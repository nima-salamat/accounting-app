"""Application entry point. Importing this module does not start the UI."""
import sys
from pathlib import Path

from accounting_app.config import ensure_data_dir
from manager.db import create_admin, create_db, initialize_database

ICON_PATH = Path(__file__).resolve().parent / "icon.ico"


def run(argv=None):
    """Initialize persistent services, then start the Qt event loop."""
    ensure_data_dir()
    initialize_database()
    create_db()
    create_admin()

    from PySide2.QtCore import Qt
    from PySide2.QtGui import QIcon
    from PySide2.QtWidgets import QApplication
    from ui.main_window import MainWindow

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("Accounting App")
    app.setWindowIcon(QIcon(str(ICON_PATH)))

    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(run())
