"""Punto di ingresso dell'applicazione: python src/main.py"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Consente l'avvio diretto da sorgenti senza installare il pacchetto
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from find_document import APP_AUTHOR, APP_NAME  # noqa: E402
from find_document.gui.main_window import MainWindow  # noqa: E402
from find_document.version import get_version  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_AUTHOR)
    app.setApplicationVersion(get_version())
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
