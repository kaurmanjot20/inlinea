import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, Gdk

from pdf_app.window_manager import WindowManager

class PDFApplication(Adw.Application):
    def __init__(self, application_id='com.inlinea.app', flags=Gio.ApplicationFlags.HANDLES_OPEN):
        super().__init__(application_id=application_id, flags=flags)
        
    def do_activate(self):
        self.load_css()
        
        wm = WindowManager.get()
        win = wm.get_active_window()
        if not win:
            win = wm.create_window(self)
            
        win.present()

    def do_open(self, files, n_files, hint):
        self.do_activate()
        wm = WindowManager.get()
        win = wm.get_active_window()
        if win:
            for gfile in files:
                win.open_pdf_tab(gfile)
        
    def load_css(self):
        provider = Gtk.CssProvider()
        try:
            import os
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
                pass
        except Exception as e:
            pass

