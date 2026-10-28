"""Application entry point. Importing this module does not start the UI."""
import sys
from pathlib import Path

from accounting_app.config import ensure_data_dir
from manager.db import create_db, initialize_database

ICON_PATH = Path(__file__).resolve().parent / "icon.ico"


def run(argv=None):
    """Initialize persistent services, run setup when needed, then open the app."""
    ensure_data_dir()
    initialize_database()
    create_db()
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QDialog
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName("Accounting App")
    app.setWindowIcon(QIcon(str(ICON_PATH)))

    from accounting_app.services.installer import is_setup_required
    if is_setup_required():
        from ui.pages.installer_wizard import InitialSetupWizard

        wizard = InitialSetupWizard()
        if wizard.exec() != QDialog.Accepted or not wizard.installation_complete:
            return 0

    from ui.pages.main_window import MainWindow

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
