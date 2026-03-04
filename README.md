# Inlinea

A Linux-first, annotation-focused PDF editor built with Python, GTK 4, and Libadwaita.

**UX-first. Native. Clean. No sidecar clutter.**

## Features

- Browser-style tabs for multi-document editing
- Text highlights and underline annotations
- Area highlights with color customization
- Add-text-anywhere with inline editing
- Undo / Redo support
- Dual-page and continuous scroll view modes
- Embedded PDF annotation saving (no sidecar files)
- Flattened PDF export
- Thumbnail sidebar with lazy rendering
- Pinch-to-zoom and Ctrl+scroll zoom

## Screenshots

<!-- Add screenshots here -->

## Setup & Installation

Inlinea depends on GTK 4, Libadwaita, Poppler, Cairo, and PyMuPDF.

### Fedora / RHEL

```bash
sudo dnf install \
  gtk4-devel \
  libadwaita-devel \
  python3-gobject \
  python3-cairo \
  poppler-glib-devel \
  cairo-devel \
  python3-pymupdf
```

### Ubuntu / Debian

```bash
sudo apt install \
  libgtk-4-dev \
  libadwaita-1-dev \
  python3-gi \
  python3-cairo \
  libgirepository1.0-dev \
  libpoppler-glib-dev \
  gir1.2-poppler-0.18 \
  python3-pymupdf
```

## Running

```bash
python3 main.py
```

## Register as PDF Handler

Add Inlinea to your system's "Open With" menu:

```bash
bash install-desktop.sh
```

This copies a `.desktop` entry to `~/.local/share/applications/` so you can right-click any PDF and open it with Inlinea.

## Project Structure

```
main.py                    # Entry point
install-desktop.sh         # Desktop entry installer
com.inlinea.app.desktop    # Freedesktop .desktop file
src/
  assets/
    style.css              # Application stylesheet
  pdf_app/
    app.py                 # GTK Application class
    main.py                # Module entry point
    window.py              # Main window, tabs & ribbon
    ui/
      pdf_view.py          # Virtual-scroll PDF viewer
      page_view.py         # Per-page overlay (gestures, annotations)
      pdf_drawing_area.py  # Cairo rendering & annotation drawing
      thumbnail_sidebar.py # Lazy thumbnail grid
      empty_view.py        # Welcome screen
      text_editor.py       # Inline text editor popover
      text_dialog.py       # Text annotation dialog
    document/
      loading.py           # Poppler document loader
      render.py            # Page-to-surface renderer
      store.py             # Annotation data model & undo/redo
      pdf_storage.py       # PyMuPDF annotation I/O
      export.py            # Flattened PDF export
    utils/
      geometry.py          # Geometry helpers
```

## License

GPL-3.0
