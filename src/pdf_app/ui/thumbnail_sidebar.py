import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Gdk, Gio, GObject, Adw

from pdf_app.document.render import render_page_to_surface
import cairo

class ThumbnailObject(GObject.Object):
    def __init__(self, page, page_number):
        super().__init__()
        self.page = page
        self.page_number = page_number
        self.surface = None

class ThumbnailSidebar(Gtk.Box):
    __gsignals__ = {
        'page-selected': (GObject.SignalFlags.RUN_FIRST, None, (int,))
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_size_request(200, -1)
        self._programmatic_update = False
        

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
        if not document:
            return
            
        n_pages = document.get_n_pages()
        for i in range(n_pages):
            page = document.get_page(i)
            thumb = ThumbnailObject(page, i)
            self.store.append(thumb)

    def select_page(self, index):
        if index != self.selection_model.get_selected():
            self._programmatic_update = True
            try:
                self.selection_model.set_selected(index)
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
        
        label.set_text(f"{thumbnail_obj.page_number + 1}")
        
        w, h = thumbnail_obj.page.get_size()
        aspect = w / h if h != 0 else 1
        thumb_w = 60
        thumb_h = int(thumb_w / aspect)
        da.set_size_request(thumb_w, thumb_h)
        
        da.set_draw_func(self.draw_thumbnail, thumbnail_obj)

    def on_unbind(self, factory, list_item):
        pass

    def draw_thumbnail(self, da, c, w, h, thumbnail_obj):
        if thumbnail_obj.surface is None:
             page_w, page_h = thumbnail_obj.page.get_size()
             scale = w / page_w
             
             surface = render_page_to_surface(thumbnail_obj.page, scale=scale)
             thumbnail_obj.surface = surface
             
        if thumbnail_obj.surface:
             c.set_source_surface(thumbnail_obj.surface, 0, 0)
             c.paint()
