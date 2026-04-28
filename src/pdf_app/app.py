import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, Gdk

from pdf_app.window_manager import WindowManager
from pdf_app.session_manager import SessionManager

class PDFApplication(Adw.Application):
    def __init__(self, application_id='com.inlinea.app', flags=Gio.ApplicationFlags.HANDLES_OPEN):
        super().__init__(application_id=application_id, flags=flags)
        self._session_restored = False
        
    def do_activate(self):
        self.load_css()
        
        wm = WindowManager.get()
        win = wm.get_active_window()

        # First launch with no windows — attempt session restore
        if not win and not self._session_restored:
            self._session_restored = True
            restored = self._try_restore_session()
            if restored:
                return

        if not win:
            win = wm.create_window(self)
            
        win.present()

    def _try_restore_session(self):
        """Attempt to restore a saved session.  Returns True if windows were created."""
        sm = SessionManager.get()
        session = sm.load_session()
        if not session or not session.get("windows"):
            return False

        was_crash = not session.get("clean_exit", True)

        wm = WindowManager.get()
        first_window = None

        for win_data in session["windows"]:
            if not win_data.get("tabs"):
                continue
            win = wm.create_window(self, add_initial_tab=False)
            win.present()
            win.restore_session_tabs(win_data)
            if first_window is None:
                first_window = win

        if first_window is None:
            return False

        # Mark session as unclean while running (crash detection)
        sm.set_clean_exit(False)

        if was_crash:
            toast = Adw.Toast.new("Previous session restored after unexpected shutdown")
            toast.set_timeout(5)
            first_window.toast_overlay.add_toast(toast)

        return True

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

