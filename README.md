# <img src="src/assets/images/inlinea.png" width="32" height="32" align="center"> Inlinea

**The Linux-first, native, and clean PDF editor.**

Built with Python, GTK 4, and Libadwaita, Inlinea is designed for users who need a fast, distraction-free environment for reading and annotating PDF documents.

---

## ✨ Key Features

### 🖋️ Powerful Annotations
*   **High-Fidelity Highlighting:** Smooth, multi-line text highlights and underlines.
*   **Area Selection:** Draw boxes to highlight specific diagrams or regions.
*   **Inline Text Editing:** Add text anywhere on the page with a clean popup editor.
*   **Custom Colors:** Personalize your annotations with an integrated color picker.

### 📖 Professional Viewing Experience
*   **Browser-Style Tabs:** Efficiently manage multiple documents in one window.
*   **Adaptive Layouts:** Toggle between single-page, dual-page, and continuous scroll modes.
*   **Fluid Zoom:** Precise pinch-to-zoom and Ctrl+Scroll support.
*   **Lazy Rendering:** Lightning-fast thumbnail sidebar, even for massive documents.

### 🛠️ Seamless Workflow
*   **Native PDF Standards:** Annotations are saved directly into the PDF; no sidecar files needed.
*   **Flattened Export:** Generate clean PDFs for sharing where annotations are baked into the layout.
*   **Robust Undo/Redo:** Full history support for all your edits.

---

## 📸 Preview

<p align="center">
  <img src="src/assets/images/screenshot0.png" width="49%" /> 
  <img src="src/assets/images/screenshot1.png" width="49%" />
</p>

---

## 🚀 Getting Started

### Prerequisites

Inlinea requires GTK 4, Poppler, Cairo, and PyMuPDF.

#### Fedora / RHEL
```bash
sudo dnf install \
  gtk4-devel libadwaita-devel python3-gobject \
  python3-cairo poppler-glib-devel cairo-devel python3-pymupdf
```

#### Ubuntu / Debian
```bash
sudo apt install \
  libgtk-4-dev libadwaita-1-dev python3-gi python3-cairo \
  libgirepository1.0-dev libpoppler-glib-dev gir1.2-poppler-0.18 python3-pymupdf
```

### Running Locally

Clone the repository and run:
```bash
python3 main.py
```

### Desktop Integration

To add Inlinea to your system's "Open With" menu and register it as a PDF handler:
```bash
bash install-desktop.sh
```
This installs a `.desktop` entry to `~/.local/share/applications/`.

---

## 🤝 Contributing

Contributions are welcome! If you have a feature request or found a bug, please check out our [Contributing Guidelines](CONTRIBUTING.md).

## 📄 License

This project is licensed under the MIT License.
License
