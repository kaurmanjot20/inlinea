"""
SessionManager — Singleton that handles session persistence.

Saves and restores the full workspace state (windows, tabs, scroll/zoom
positions, active tabs) to a JSON file in ~/.local/share/inlinea/.

Uses debounced auto-save so rapid changes (tab switches, drag-and-drop)
don't hammer disk I/O.
"""

import json
import logging
import os
import time
from gi.repository import GLib

logger = logging.getLogger(__name__)


SESSION_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "inlinea",
)
SESSION_FILE = os.path.join(SESSION_DIR, "session.json")

# Current schema version for forward compatibility
SESSION_VERSION = 1


class SessionManager:
    """Global session persistence manager."""

    _instance = None

    @classmethod
    def get(cls):
        """Return the singleton SessionManager instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._save_source_id = 0  # GLib timeout source for debounce

    # ========== Public API ==========

    def schedule_save(self):
        """Schedule a debounced session save (500 ms).

        Multiple calls within the debounce window are coalesced into
        a single write.
        """
        if self._save_source_id:
            GLib.source_remove(self._save_source_id)
        self._save_source_id = GLib.timeout_add(500, self._do_save)

    def save_now(self, clean_exit=True):
        """Immediately save the session (used on app shutdown)."""
        # Cancel any pending debounced save
        if self._save_source_id:
            GLib.source_remove(self._save_source_id)
            self._save_source_id = 0
        self._write_session(clean_exit=clean_exit)

    def load_session(self):
        """Load and return the saved session dict, or None."""
        if not os.path.exists(SESSION_FILE):
            return None
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") != SESSION_VERSION:
                return None
            return data
        except (json.JSONDecodeError, OSError, KeyError):
            logger.warning("Could not read session file %s", SESSION_FILE, exc_info=True)
            return None

    def clear_session(self):
        """Remove the session file after a successful restore."""
        try:
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
        except OSError:
            pass

    def set_clean_exit(self, clean):
        """Update the clean_exit flag in the existing session file.

        This is called on startup (set False) and shutdown (set True) so
        that an unexpected crash leaves clean_exit=False for recovery.
        """
        data = self.load_session()
        if data is None:
            return
        data["clean_exit"] = clean
        self._write_json(data)

    # ========== Internal ==========

    def _do_save(self):
        """GLib timeout callback — performs the actual save."""
        self._save_source_id = 0
        self._write_session(clean_exit=False)
        return False  # Don't repeat

    def _write_session(self, clean_exit=True):
        """Collect state from all windows and write to disk."""
        from inlinea.window_manager import WindowManager
        from inlinea.ui.pdf_view import PDFView

        wm = WindowManager.get()
        windows_data = []

        for win in wm.windows:
            win_state = win.get_session_state()
            # Only save windows that have at least one real PDF tab
            if win_state["tabs"]:
                windows_data.append(win_state)

        if not windows_data:
            # Nothing to save — remove stale session file
            self.clear_session()
            return

        session = {
            "version": SESSION_VERSION,
            "clean_exit": clean_exit,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "windows": windows_data,
        }

        self._write_json(session)

    def _write_json(self, data):
        """Atomically write JSON data to the session file."""
        os.makedirs(SESSION_DIR, exist_ok=True)
        tmp_path = SESSION_FILE + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, SESSION_FILE)
        except OSError:
            # Best-effort — don't crash the app over session persistence
            try:
                os.remove(tmp_path)
            except OSError:
                pass
