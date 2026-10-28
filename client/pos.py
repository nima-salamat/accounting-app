"""Standalone point-of-sale client: `python -m client.pos`."""
import os
import uuid

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from client.ui.auth_page import AuthPage
from client.ui.permissions import can_access
from client.ui.sales_page import SalesPage
from client.ui.theme import stylesheet
from client.ui.worker import ApiWorker


class POSWindow(QMainWindow):
    """A focused cash-register shell that shares the same server and invoice flow."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Accounting App · صندوق فروش")
        self.resize(1180, 780)
        self.setMinimumSize(880, 620)
        self.mode = os.environ.get("ACCOUNTING_APP_THEME", "light").lower()
        if self.mode not in ("light", "dark"):
            self.mode = "light"
        self.api = None
        self.current_user = None
        self._workers = {}
        self._callbacks = {}
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.stack = QStackedWidget(self)
        self.auth_page = AuthPage(self.mode, self)
        self.auth_page.authenticated.connect(self._authenticated)
        self.auth_page.api_changed.connect(self._api_changed)
        self.auth_page.theme_changed.connect(self.change_theme)
        self.stack.addWidget(self.auth_page)

        self.sales_page = SalesPage(self)
        sales_host = QWidget()
        sales_host.setObjectName("AppRoot")
        sales_layout = QVBoxLayout(sales_host)
        sales_layout.setContentsMargins(12, 12, 12, 12)
        sales_layout.setSpacing(10)
        topbar = QFrame()
        topbar.setObjectName("Card")
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(16, 10, 16, 10)
        title = QLabel("صندوق فروش")
        title.setObjectName("PageTitle")
        self.status = QLabel("برای شروع وارد حساب کاربری شوید.")
        self.status.setObjectName("PageSubtitle")
        top_layout.addWidget(title)
        top_layout.addStretch(1)
        top_layout.addWidget(self.status)
        self.logout_button = QPushButton("خروج")
        self.logout_button.setObjectName("DangerButton")
        self.logout_button.clicked.connect(self.logout)
        top_layout.addWidget(self.logout_button)
        sales_layout.addWidget(topbar)
        sales_layout.addWidget(self.sales_page, 1)
        self.stack.addWidget(sales_host)
        self.setCentralWidget(self.stack)
        self.stack.setCurrentWidget(self.auth_page)
        self.setStyleSheet(stylesheet(self.mode))

    def _api_changed(self, api):
        self.api = api

    def _authenticated(self, user):
        self.current_user = user
        self.api = self.auth_page.api
        if not can_access(user, "sales", "create"):
            self.stack.setCurrentWidget(self.auth_page)
            QMessageBox.warning(
                self, "دسترسی صندوق فروش",
                "این حساب مجوز ثبت فروش ندارد. از مدیر بخواهید مجوز «فروش / ایجاد» را فعال کند.",
            )
            return
        self.stack.setCurrentIndex(1)
        self.set_status("صندوق آماده است · کاربر {}".format(user.get("username", "")))
        self.sales_page.refresh_products()

    def set_status(self, message):
        self.status.setText(str(message))

    def refresh_dashboard_data(self):
        # The focused POS app intentionally does not load accounting dashboards.
        return None

    def run_api(self, operation, on_success, *, failure=None, busy=None):
        ticket = uuid.uuid4().hex
        worker = ApiWorker(operation, ticket, parent=self)
        self._workers[ticket] = worker
        self._callbacks[ticket] = (on_success, failure, busy)
        worker.succeeded.connect(self._worker_success)
        worker.failed.connect(self._worker_failure)
        worker.finished.connect(lambda: self._cleanup_worker(ticket))
        if busy:
            busy.setEnabled(False)
        worker.start()

    @Slot(str, object)
    def _worker_success(self, ticket, result):
        callback = self._callbacks.pop(ticket, None)
        if callback:
            success, _failure, busy = callback
            if busy:
                busy.setEnabled(True)
            success(result)

    @Slot(str, object)
    def _worker_failure(self, ticket, error):
        callback = self._callbacks.pop(ticket, None)
        if callback:
            _success, failure, busy = callback
            if busy:
                busy.setEnabled(True)
            if failure:
                failure(error)
            else:
                self.show_error(error)

    def _cleanup_worker(self, ticket):
        worker = self._workers.pop(ticket, None)
        if worker:
            worker.deleteLater()

    def show_error(self, error):
        if getattr(error, "status_code", None) == 401:
            self.force_logout()
        QMessageBox.warning(self, "خطای صندوق فروش", str(error))

    def logout(self):
        if self.api is None:
            self.force_logout()
            return
        self.run_api(self.api.logout, lambda _result: self.force_logout(),
                     failure=lambda _error: self.force_logout())

    def force_logout(self):
        if self.api is not None:
            self.api.clear_session()
        self.current_user = None
        self.auth_page.api = self.api
        if self.api is not None:
            self.auth_page.server_url.setText(self.api.base_url)
        self.stack.setCurrentWidget(self.auth_page)
        self.auth_page.set_mode(self.mode)
        self.auth_page.connect_server()

    def change_theme(self, mode):
        if mode not in ("light", "dark"):
            return
        self.mode = mode
        os.environ["ACCOUNTING_APP_THEME"] = mode
        self.setStyleSheet(stylesheet(mode))
        self.auth_page.set_mode(mode)

    def closeEvent(self, event):
        for worker in list(self._workers.values()):
            if worker.isRunning():
                worker.wait(35000)
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Accounting App POS")
    window = POSWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
