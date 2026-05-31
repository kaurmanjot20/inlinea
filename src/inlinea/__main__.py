import logging
import os
import sys


def main():
    # stderr only — no log file written; journald captures this when launched from desktop
    level = logging.DEBUG if os.environ.get("INLINEA_DEBUG") else logging.WARNING
    logging.basicConfig(
        stream=sys.stderr, level=level, format="%(name)s %(levelname)s: %(message)s"
    )
    os.environ["GSK_RENDERER"] = "cairo"
    from inlinea.app import PDFApplication

    app = PDFApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
