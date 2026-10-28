"""Background network jobs; no HTTP request blocks the Qt event loop."""
import uuid

from PySide6.QtCore import QThread, Signal, Slot


class ApiWorker(QThread):
    succeeded = Signal(str, object)
    failed = Signal(str, object)

    def __init__(self, operation, ticket=None, parent=None):
        super().__init__(parent)
        self.ticket = ticket or uuid.uuid4().hex
        self.operation = operation

    def run(self):
        try:
            self.succeeded.emit(self.ticket, self.operation())
        except Exception as exc:
            self.failed.emit(self.ticket, exc)
