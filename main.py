
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from pdf_app.app import PDFApplication

def main():
    os.environ["GSK_RENDERER"] = "cairo"
    
    app = PDFApplication()
    return app.run(sys.argv)

if __name__ == '__main__':
    sys.exit(main())
