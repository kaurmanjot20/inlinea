import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Adw

class EmptyView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        
        label = Gtk.Label(label="Welcome to Inlinea")
        label.add_css_class("title-1")
        
        sub = Gtk.Label(label="Open a PDF to start annotating.")
        sub.add_css_class("body")
        
        self.append(label)
        self.append(sub)
        
        # Open button would be nice here
        btn_open = Gtk.Button(label="Open PDF")
        btn_open.add_css_class("pill")
        btn_open.add_css_class("suggested-action")
        btn_open.set_action_name("win.open_document")
        self.append(btn_open)
