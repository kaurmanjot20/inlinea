import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk

class TextEditorPopover(Gtk.Popover):
    def __init__(self, parent_widget, annotation, on_update):
        super().__init__()
        self.set_parent(parent_widget)
        self.annotation = annotation
        self.on_update = on_update
        self.parent_widget = parent_widget # Usually DrawingArea
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(4)
        self.set_child(box)
        
        # Text Area
        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.get_buffer().set_text(annotation.content)
        self.text_view.get_buffer().connect("changed", self.on_text_changed)
        # Font styling for editor can match drawing area later
        
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.text_view)
        scroll.set_min_content_width(200)
        scroll.set_min_content_height(100)
        scroll.set_max_content_width(400)
        scroll.set_max_content_height(300)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        box.append(scroll)
        
        self.set_position(Gtk.PositionType.TOP)
        self.set_autohide(True)
        
    def update_position(self, scale):
        if not self.annotation.rects:
            return
            
        x, y, w, h = self.annotation.rects[0]
        
        rect = Gdk.Rectangle()
        rect.x = int(x * scale)
        rect.y = int(y * scale)
        rect.width = int(w * scale)
    
        if rect.width < 10: rect.width = 10
        if rect.height < 10: rect.height = 10
            
        self.set_pointing_to(rect)
        
    def on_text_changed(self, buffer):
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        self.annotation.content = text
        if self.on_update:
            self.on_update(self.annotation)
