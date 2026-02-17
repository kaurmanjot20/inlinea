import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, Gio, GObject, Adw

from pdf_app.document.render import render_page_to_surface
import cairo

class ThumbnailObject(GObject.Object):
    """Ref-counted object to hold page data for the ListStore."""
    def __init__(self, page, page_number):
        super().__init__()
        self.page = page
        self.page_number = page_number
        self.surface = None # Cached surface

class ThumbnailSidebar(Gtk.Box):
    __gsignals__ = {
        'page-selected': (GObject.SignalFlags.RUN_FIRST, None, (int,))
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        # Fix: GTK4 uses set_size_request for min size
        self.set_size_request(200, -1)
        
        self._programmatic_update = False
        


        # Scrolled Window
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        # GTK4: set_policy(h_policy, v_policy)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.append(self.scrolled)

        # List View Setup
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
        
        self._current_scale = 0.2 # Thumbnail scale relative to original

    def set_dual_mode(self, enabled):
        """Toggle between single and dual column grid."""
        cols = 2 if enabled else 1
        self.grid_view.set_min_columns(cols)
        self.grid_view.set_max_columns(cols)
        
    def load_document(self, document):
        self.store.remove_all()
        if not document:
            return
            
        n_pages = document.get_n_pages()
        for i in range(n_pages):
            page = document.get_page(i)
            thumb = ThumbnailObject(page, i)
            self.store.append(thumb)

    def select_page(self, index):
        """Programmatically select a page."""
        if index != self.selection_model.get_selected():
            self._programmatic_update = True
            try:
                self.selection_model.set_selected(index)
            finally:
                self._programmatic_update = False
            # Scroll to it?
            # self.list_view.scroll_to_item(index) # Need widget-specific logic

    def on_selection_changed(self, model, param):
        # Selection change is purely visual (handled by CSS/State).
        # We DO NOT trigger navigation here to avoid feedback loops and unintended scrolling.
        # Navigation is handled exclusively by 'activate' (click).
        pass

    def on_activate(self, list_view, position):
        self.emit('page-selected', position)

    # --- Factory Methods ---
    def on_setup(self, factory, list_item):
        """Create widget structure for a grid item."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(4)
        
        # DrawingArea for Thumbnail
        da = Gtk.DrawingArea()
        da.set_size_request(60, 80) # Initial size
        da.set_halign(Gtk.Align.CENTER)
        
        # Label for Page Number
        label = Gtk.Label()
        label.set_css_classes(["caption"])
        
        box.append(da)
        box.append(label)
        
        list_item.set_child(box)

    def on_bind(self, factory, list_item):
        """Bind data to the widgets."""
        box = list_item.get_child()
        if not box:
            return # Should not happen if setup succeeds
            
        da = box.get_first_child()
        label = da.get_next_sibling()
        
        thumbnail_obj = list_item.get_item()
        
        # Set text
        label.set_text(f"{thumbnail_obj.page_number + 1}")
        
        # Calculate aspect ratio for DA size
        w, h = thumbnail_obj.page.get_size()
        aspect = w / h if h != 0 else 1
        thumb_w = 60
        thumb_h = int(thumb_w / aspect)
        da.set_size_request(thumb_w, thumb_h)
        
        # Set Draw Function
        da.set_draw_func(self.draw_thumbnail, thumbnail_obj)

    def on_unbind(self, factory, list_item):
        # Optional cleanup
        pass

    def draw_thumbnail(self, da, c, w, h, thumbnail_obj):
        # Use cached surface if available
        if thumbnail_obj.surface is None:
             # Render!
             # Calculate scale to fit width
             page_w, page_h = thumbnail_obj.page.get_size()
             scale = w / page_w
             
             surface = render_page_to_surface(thumbnail_obj.page, scale=scale)
             thumbnail_obj.surface = surface
             
        # Paint
        if thumbnail_obj.surface:
             c.set_source_surface(thumbnail_obj.surface, 0, 0)
             c.paint()
