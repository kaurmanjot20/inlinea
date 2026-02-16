import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, Gdk

from pdf_app.window import MainWindow

class PDFApplication(Adw.Application):
    def __init__(self, application_id='com.inlinea.app', flags=Gio.ApplicationFlags.FLAGS_NONE):
        super().__init__(application_id=application_id, flags=flags)
        
    def do_activate(self):
        """Called when the application is activated (e.g., launched)."""
        
        # Load CSS (Safe to do here)
        self.load_css()
        
        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
            
        win.present()
        
    def load_css(self):
        provider = Gtk.CssProvider()
        try:
            import os
            # Try multiple paths
            paths = [
                os.path.join(os.path.dirname(__file__), "../assets/style.css"),
                "src/assets/style.css",
                "assets/style.css"
            ]
            
            css_path = None
            for p in paths:
                if os.path.exists(p):
                    css_path = p
                    break
            
            if css_path:
                provider.load_from_path(css_path)
                display = Gdk.Display.get_default()
                Gtk.StyleContext.add_provider_for_display(
                    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            else:
                pass  # CSS file not found
        except Exception as e:
            pass  # CSS loading error
