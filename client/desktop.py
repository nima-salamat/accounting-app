"""Launch the API-only PySide6 desktop client."""
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from client.ui.main_window import AccountingMainWindow
from client.ui.theme import install_spinbox_wheel_guard


def main(argv=None):
    app = QApplication(sys.argv if argv is None else argv)
    install_spinbox_wheel_guard(app)
    app.setApplicationName("Accounting App")
    icon_path = Path(__file__).resolve().parents[1] / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = AccountingMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
