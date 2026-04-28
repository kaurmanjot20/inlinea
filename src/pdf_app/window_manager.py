"""
WindowManager — Singleton that tracks all open InlineaWindow instances
and the currently active (focused) window.

Used by PDFApplication to route new file opens to the active window,
and by InlineaWindow to create new windows when tabs are detached.
"""


class WindowManager:
    """Global registry for all open application windows."""

    _instance = None

    @classmethod
    def get(cls):
        """Return the singleton WindowManager instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.windows = []          # List of InlineaWindow
        self.active_window = None  # Last focused InlineaWindow

    # ========== Registry ==========

    def register(self, window):
        """Register a newly created window."""
        if window not in self.windows:
            self.windows.append(window)
        self.active_window = window

    def unregister(self, window):
        """Unregister a window that is being destroyed."""
        if window in self.windows:
            self.windows.remove(window)
        if self.active_window == window:
            self.active_window = self.windows[-1] if self.windows else None

    # ========== Focus Tracking ==========

    def set_active(self, window):
        """Update the active window (called on focus-in)."""
        if window in self.windows:
            self.active_window = window

    def get_active_window(self):
        """Return the currently active window, or None."""
        return self.active_window

    # ========== Window Creation ==========

    def create_window(self, app, add_initial_tab=True):
        """Create a new InlineaWindow, register it, and return it.
        
        Args:
            app: The PDFApplication instance.
            add_initial_tab: If False, skip adding the empty welcome tab.
                            Used when creating windows for detached tabs.
        """
        from pdf_app.window import InlineaWindow
        win = InlineaWindow(application=app, add_initial_tab=add_initial_tab)
        return win
