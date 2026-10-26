from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler("soundtotext.log", encoding="utf-8")],
    )
    app = QApplication(sys.argv)
    app.setApplicationName("SoundtoText")
    app.setOrganizationName("SoundtoText")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
