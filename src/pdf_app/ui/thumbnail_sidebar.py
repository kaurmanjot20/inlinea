import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, Gio, GObject, Adw, GLib

from pdf_app.document.render import render_page_to_surface
import cairo

class ThumbnailObject(GObject.Object):
    def __init__(self, document, page_number):
        super().__init__()
        self.document = document
        self.page_number = page_number
        self.surface = None
        self._idle_source_id = 0   # GLib source ID for pending render
        self._bound = False        # Whether currently bound to a visible widget

class ThumbnailSidebar(Gtk.Box):
    __gsignals__ = {
        'page-selected': (GObject.SignalFlags.RUN_FIRST, None, (int,))
    }

    # Only 1 concurrent thumbnail render so Poppler doesn't starve the UI event loop
    _MAX_CONCURRENT_RENDERS = 1
    _active_renders = 0
    _RENDER_INTERVAL_MS = 150  # Gap between renders to keep UI responsive

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_size_request(200, -1)
        self._programmatic_update = False

        self._render_queue = []

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(self.scrolled)

        self.store = Gio.ListStore(item_type=ThumbnailObject)
        self.selection_model = Gtk.SingleSelection(model=self.store)
        self.selection_model.connect("notify::selected", self.on_selection_changed)
        
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.on_setup)
        factory.connect("bind", self.on_bind)
        factory.connect("unbind", self.on_unbind)
        
        self.grid_view = Gtk.GridView(model=self.selection_model, factory=factory)
        self.grid_view.set_max_columns(1)
        self.grid_view.set_min_columns(1)
        self.grid_view.set_single_click_activate(True)
        self.grid_view.connect("activate", self.on_activate)
        
        self.scrolled.set_child(self.grid_view)
        
        self._current_scale = 0.2

    def set_dual_mode(self, enabled):
        cols = 2 if enabled else 1
        self.grid_view.set_min_columns(cols)
        self.grid_view.set_max_columns(cols)
        
    def load_document(self, document):
        self.store.remove_all()
        self._render_queue.clear()
        ThumbnailSidebar._active_renders = 0
        self._render_started = False
        if not document:
            return
            
        self.document = document
        n_pages = document.get_n_pages()

        for i in range(n_pages):
            self.store.append(ThumbnailObject(self.document, i))

        # Delay thumbnail rendering by 2s so main-view pages load without competition
        GLib.timeout_add(2000, self._start_rendering)

    def select_page(self, index):
        if index != self.selection_model.get_selected():
            self._programmatic_update = True
            try:
                self.selection_model.set_selected(index)
                # Auto-scroll the sidebar to show the current page thumbnail
                n_items = self.store.get_n_items()
                if hasattr(self.grid_view, 'scroll_to') and index < n_items:
                    self.grid_view.scroll_to(index, Gtk.ListScrollFlags.NONE, None)
                elif n_items > 0:
                    # Fallback for GTK < 4.12: estimate scroll position
                    n_items = self.store.get_n_items()
                    if n_items > 0:
                        vadj = self.scrolled.get_vadjustment()
                        fraction = index / max(1, n_items - 1)
                        max_val = vadj.get_upper() - vadj.get_page_size()
                        vadj.set_value(fraction * max(0, max_val))
            finally:
                self._programmatic_update = False

    def on_selection_changed(self, model, param):
        pass

    def on_activate(self, list_view, position):
        self.emit('page-selected', position)

    # --- Factory Methods ---
    def on_setup(self, factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(4)
        
        # DrawingArea for Thumbnail
        da = Gtk.DrawingArea()
        da.set_size_request(60, 80) 
        da.set_halign(Gtk.Align.CENTER)
        
        label = Gtk.Label()
        label.set_css_classes(["caption"])
        
        box.append(da)
        box.append(label)
        
        list_item.set_child(box)

    def on_bind(self, factory, list_item):
        box = list_item.get_child()
        if not box:
            return 
            
        da = box.get_first_child()
        label = da.get_next_sibling()
        
        thumbnail_obj = list_item.get_item()
        thumbnail_obj._bound = True
        
        label.set_text(f"{thumbnail_obj.page_number + 1}")
        
        # JIT fetch to get size, then let it drop out of scope to prevent OOM
        temp_page = thumbnail_obj.document.get_page(thumbnail_obj.page_number)
        w, h = temp_page.get_size()
        aspect = w / h if h != 0 else 1
        thumb_w = 60
        thumb_h = int(thumb_w / aspect)
        da.set_size_request(thumb_w, thumb_h)
        
        da.set_draw_func(self.draw_thumbnail, thumbnail_obj)
        
        # Store references for deferred rendering
        thumbnail_obj._draw_area = da
        thumbnail_obj._page_w = w
        thumbnail_obj._thumb_w = thumb_w
        
        # Only enqueue rendering after the initial delay has passed
        if self._render_started and thumbnail_obj.surface is None:
            self._enqueue_render(thumbnail_obj, w, da, thumb_w)

    def _start_rendering(self):
        self._render_started = True
        for i in range(self.store.get_n_items()):
            item = self.store.get_item(i)
            if (item and item._bound and item.surface is None
                    and hasattr(item, '_draw_area') and item._draw_area):
                self._enqueue_render(item, item._page_w, item._draw_area, item._thumb_w)
        return False

    def _enqueue_render(self, t_obj, page_w, draw_area, thumb_w):
        if ThumbnailSidebar._active_renders < ThumbnailSidebar._MAX_CONCURRENT_RENDERS:
            ThumbnailSidebar._active_renders += 1
            sid = GLib.timeout_add(ThumbnailSidebar._RENDER_INTERVAL_MS,
                                   self._render_thumb_idle, t_obj, page_w, draw_area, thumb_w)
            t_obj._idle_source_id = sid
        else:
            self._render_queue.append((t_obj, page_w, draw_area, thumb_w))

    def _render_thumb_idle(self, t_obj, page_w, draw_area, tw):
        """Render one thumbnail, then drain the queue."""
        t_obj._idle_source_id = 0
        try:
            # Skip if the widget was unbound before this fired
            if not t_obj._bound or not draw_area.get_parent():
                return False
            scale = tw / page_w
            temp = t_obj.document.get_page(t_obj.page_number)
            surface = render_page_to_surface(temp, scale=scale)
            t_obj.surface = surface
            draw_area.queue_draw()
        finally:
            ThumbnailSidebar._active_renders = max(0, ThumbnailSidebar._active_renders - 1)
            self._drain_render_queue()
        return False

    def _drain_render_queue(self):
        """Start the next queued render if under the concurrency limit."""
        while (self._render_queue and
               ThumbnailSidebar._active_renders < ThumbnailSidebar._MAX_CONCURRENT_RENDERS):
            t_obj, page_w, draw_area, thumb_w = self._render_queue.pop(0)
            
            if not t_obj._bound or not draw_area.get_parent():
                continue
            ThumbnailSidebar._active_renders += 1
            sid = GLib.timeout_add(ThumbnailSidebar._RENDER_INTERVAL_MS,
                                   self._render_thumb_idle, t_obj, page_w, draw_area, thumb_w)
            t_obj._idle_source_id = sid
            break

    def on_unbind(self, factory, list_item):
        # Cancel any pending idle render BEFORE it fires
        item = list_item.get_item()
        if item:
            item._bound = False
            item._draw_area = None
            if item._idle_source_id:
                GLib.source_remove(item._idle_source_id)
                item._idle_source_id = 0
                ThumbnailSidebar._active_renders = max(0, ThumbnailSidebar._active_renders - 1)
                self._drain_render_queue()
            item.surface = None

        # Clear draw func to prevent memory buildup
        box = list_item.get_child()
        if box:
            da = box.get_first_child()
            if da:
                da.set_draw_func(None)

    def draw_thumbnail(self, da, c, w, h, thumbnail_obj):
        if thumbnail_obj.surface:
            c.set_source_surface(thumbnail_obj.surface, 0, 0)
            c.paint()
        else:
            c.set_source_rgb(0.92, 0.92, 0.92)
            c.paint()

