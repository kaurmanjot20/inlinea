import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Pango

class TextAnnotationDialog(Gtk.Window):
    def __init__(self, parent_window):
        super().__init__()
        self.set_title("Add Note")
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_default_size(400, 300)
        
        self.callback = None
        
        # Main Layout
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root_box.set_margin_top(20)
        root_box.set_margin_bottom(20)
        root_box.set_margin_start(20)
        root_box.set_margin_end(20)
        self.set_child(root_box)
        
        # Title
        title = Gtk.Label(label="Add Text Annotation")
        title.add_css_class("title-2")
        root_box.append(title)
        
        # Text Input
        frame = Gtk.Frame()
        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text_view.set_vexpand(True)
        
        # Scrolling
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(150)
        scroll.set_child(self.text_view)
        frame.set_child(scroll)
        root_box.append(frame)
        
        # Style Toggle
        style_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        style_label = Gtk.Label(label="Style:")
        style_box.append(style_label)
        
        self.btn_standard = Gtk.ToggleButton(label="Standard")
        self.btn_handwritten = Gtk.ToggleButton(label="Handwritten")
        self.btn_handwritten.set_group(self.btn_standard)
        
        self.btn_standard.set_active(True) 
        
        style_box.append(self.btn_standard)
        style_box.append(self.btn_handwritten)
        root_box.append(style_box)
        
        # Actions
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.END)
        
        btn_cancel = Gtk.Button(label="Cancel")
        btn_cancel.connect("clicked", self.on_cancel)
        
        btn_add = Gtk.Button(label="Add")
        btn_add.add_css_class("suggested-action")
        btn_add.connect("clicked", self.on_add)
        
        action_box.append(btn_cancel)
        action_box.append(btn_add)
        root_box.append(action_box)

    def run(self, callback):
        self.callback = callback
        self.present()

    def on_cancel(self, btn):
        self.close()

    def on_add(self, btn):
        buffer = self.text_view.get_buffer()
        start, end = buffer.get_bounds()
        text = buffer.get_text(start, end, True)
        
        style = "standard"
        if self.btn_handwritten.get_active():
            style = "handwritten"
            
        if self.callback:
            self.callback(text, style)
            
        self.close()
