#!/usr/bin/env python3
"""
Entry point for Inlinea — PDF Annotation Editor.
Run this file from the project root to start the application.
"""
import sys
import os

# Add src to Python path so pdf_app package can be found
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pdf_app.app import PDFApplication

def main():
    """Application entry point."""
    app = PDFApplication()
    return app.run(sys.argv)

if __name__ == '__main__':
    sys.exit(main())
