import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, Gio, GObject, Adw, GLib

from pdf_app.document.engine import dispatch_render_job, RenderContext, RenderPriority
import cairo

class ThumbnailObject(GObject.Object):
    def __init__(self, document, uri, page_number):
        super().__init__()
        self.document = document
        self.uri = uri
        self.page_number = page_number
        self.surface = None
        self._bound = False
        self._render_token = None
        self._draw_area = None
        self._page_w = 0
        self._thumb_w = 60

class ThumbnailSidebar(Gtk.Box):
    __gsignals__ = {
        'page-selected': (GObject.SignalFlags.RUN_FIRST, None, (int,))
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_size_request(200, -1)
        self._programmatic_update = False
        self._render_started = False

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
        
    def load_document(self, document, uri):
        self.store.remove_all()
        self._render_started = False
        if not document:
            return
            
        self.document = document
        self.uri = uri
        n_pages = document.get_n_pages()

        for i in range(n_pages):
            self.store.append(ThumbnailObject(self.document, self.uri, i))

        # Delay thumbnail rendering by 2s so main-view pages load first
        GLib.timeout_add(2000, self._start_rendering)

    def select_page(self, index):
        if index != self.selection_model.get_selected():
            self._programmatic_update = True
            try:
                self.selection_model.set_selected(index)
                n_items = self.store.get_n_items()
                if hasattr(self.grid_view, 'scroll_to') and index < n_items:
                    self.grid_view.scroll_to(index, Gtk.ListScrollFlags.NONE, None)
                elif n_items > 0:
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
        
        # Get page dimensions for aspect ratio
        temp_page = thumbnail_obj.document.get_page(thumbnail_obj.page_number)
        w, h = temp_page.get_size()
        aspect = w / h if h != 0 else 1
        thumb_w = 60
        thumb_h = int(thumb_w / aspect)
        da.set_size_request(thumb_w, thumb_h)
        
        da.set_draw_func(self.draw_thumbnail, thumbnail_obj)
        
        # Store refs for deferred rendering
        thumbnail_obj._draw_area = da
        thumbnail_obj._page_w = w
        thumbnail_obj._thumb_w = thumb_w
        
        # If already rendered, just redraw. Otherwise dispatch render.
        if thumbnail_obj.surface is not None:
            da.queue_draw()
        elif self._render_started:
            self._dispatch_thumb_render(thumbnail_obj)

    def _start_rendering(self):
        """Called after 2s delay to begin thumbnail renders."""
        self._render_started = True
        for i in range(self.store.get_n_items()):
            item = self.store.get_item(i)
            if (item and item._bound and item.surface is None
                    and item._draw_area and item._page_w > 0):
                self._dispatch_thumb_render(item)
        return False

    def _dispatch_thumb_render(self, t_obj):
        """Dispatch a single thumbnail render job to the engine."""
        if t_obj._render_token:
            t_obj._render_token[0] = True
        
        t_obj._render_token = [False]
        scale = t_obj._thumb_w / t_obj._page_w if t_obj._page_w > 0 else 0.1
        
        draw_area = t_obj._draw_area
        
        def _on_thumb_done(surface, context):
            if not t_obj._bound or t_obj._render_token is None or t_obj._render_token[0]:
                return
            if surface is not None:
                t_obj.surface = surface
                if draw_area and draw_area.get_parent():
                    draw_area.queue_draw()
        
        ctx = RenderContext(scale=scale)
        dispatch_render_job(
            t_obj.uri, t_obj.page_number, ctx,
            RenderPriority.THUMBNAIL, _on_thumb_done, t_obj._render_token
        )

    def on_unbind(self, factory, list_item):
        item = list_item.get_item()
        if item:
            item._bound = False
            # Cancel pending render but keep the cached surface
            if item._render_token:
                item._render_token[0] = True
                item._render_token = None

        # Clear draw func
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
