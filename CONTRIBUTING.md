# Contributing to Inlinea 🚀

First off, thank you for considering contributing to Inlinea! It's people like you that make open-source such a great community.

## How Can I Contribute?

### Reporting Bugs 🐛
If you find a bug, please help us by opening an issue! Before creating a new issue, please check the existing issues to see if it has already been reported. 

When opening an issue, please include:
- Your operating system and version.
- The version of PyMuPDF or Poppler you are using, if relevant.
- Steps to reproduce the bug.
- Any error messages or screenshots.

### Suggesting Enhancements ✨
Have an idea for a new feature? We'd love to hear it! Open an issue to discuss your idea before writing any code. This ensures your time is spent on features that align with the project's goals.

### Code Contributions 💻
1. **Fork** the repository.
2. **Clone** your fork locally: `git clone https://github.com/your-username/inlinea.git`
3. **Create a branch** for your feature or bugfix: `git checkout -b feature/my-awesome-feature`
4. **Install dependencies**. See the "Setup & Installation" section in the `README.md` for packages required by your OS.
5. **Run the project locally** to ensure your setup works:
   ```bash
   pip install -e .
   python3 -m inlinea
   ```
6. **Make your changes**. Please try to keep your code clean and document complex logic.
7. **Commit your changes**: `git commit -m 'Add some feature'`
8. **Push to your branch**: `git push origin feature/my-awesome-feature`
9. **Open a Pull Request (PR)** against the `main` branch of this repository.

### Project Structure 📂
When making changes, it can be helpful to understand how the codebase is organized:

```text
install-desktop.sh         # Desktop entry installer
data/
  com.inlinea.app.desktop  # Freedesktop .desktop file
  icons/
    inlinea.png            # Application icon
src/
  inlinea/
    __main__.py            # Entry point (python3 -m inlinea)
    app.py                 # GTK Application class
    window.py              # Main window, tabs & ribbon
    window_manager.py      # Singleton tracking open windows
    session_manager.py     # JSON snapshot of windows/tabs/scroll/zoom
    assets/
      style.css            # Application stylesheet
    ui/
      pdf_view.py          # Virtual-scroll PDF viewer
      page_view.py         # Per-page overlay (gestures, annotations)
      pdf_drawing_area.py  # Cairo rendering & annotation drawing
      thumbnail_sidebar.py # Lazy thumbnail grid
      empty_view.py        # Welcome screen
      text_dialog.py       # Text annotation dialog
      text_toolbar.py      # Text formatting popover
    document/
      loading.py           # Poppler document loader
      store.py             # Annotation data model & undo/redo
      pdf_storage.py       # PyMuPDF annotation I/O
      export.py            # Flattened PDF export
      engine/
        pool.py            # Render-worker thread pool
        job.py             # Render-job dataclass
        context.py         # Render context (scale, rotation, dpi)
    utils/
      geometry.py          # Geometry helpers
      links.py             # URL safety & embedded link extraction
```

## Pull Request Process & Merging Rules 🚨

To keep the codebase stable, **direct commits to the `main` branch by external contributors are not allowed**. 

All changes must go through a Pull Request. Here is how it works:
- **Review Required:** Your PR must be reviewed and approved by a maintainer before it can be merged.
- **Passes Checks:** Any automated tests or build checks must pass.
- **Merge Rights:** **External contributors cannot click the "Merge" button themselves.** Once approved, a repository maintainer will merge the PR for you.


Thank you for your interest in making Inlinea better!
