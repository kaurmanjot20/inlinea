import sys
import os


def main():
    os.environ["GSK_RENDERER"] = "cairo"
    from inlinea.app import PDFApplication
    app = PDFApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
