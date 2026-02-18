import sys
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio

from pdf_app.app import PDFApplication

def main():
    app = PDFApplication()
    return app.run(sys.argv)

if __name__ == '__main__':
    sys.exit(main())
