# PDF Annotation Workspace (Linux)

A professional, UX-first PDF annotation tool built with Python, GTK 4, and Libadwaita.

## Setup & Installation

### 1. System Dependencies
This application requires GTK 4, Libadwaita, Poppler, and Cairo development headers.

**Fedora / RHEL:**
```bash
sudo dnf install gtk4-devel libadwaita-devel python3-gobject python3-cairo poppler-glib-devel cairo-devel python3-pip python3-pymupdf
```

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install libgtk-4-dev libadwaita-1-dev python3-gi python3-full python3-cairo libcairo2-dev libgirepository1.0-dev libpoppler-glib-dev gir1.2-poppler-0.18 python3-pip python3-pymupdf
```

## Running the Application

```bash
python3 main.py
```

## Project Structure
- `main.py`: Application entry point
- `src/pdf_app/`: Main source code
    - `app.py`: GTK Application class
    - `window.py`: Main application window
    - `ui/`: GTK 4 widgets and UI components
    - `document/`: PDF loading and rendering logic
    - `utils/`: Helper functions
