import logging
import gi
gi.require_version('Poppler', '0.18')
from gi.repository import Poppler, Gio, GLib

logger = logging.getLogger(__name__)

def load_document(file: Gio.File, password: str = None) -> Poppler.Document:
    uri = file.get_uri()
    try:
        document = Poppler.Document.new_from_file(uri, password)
        return document
    except GLib.Error:
        logger.warning("Could not open %s via Poppler", uri, exc_info=True)
        return None
