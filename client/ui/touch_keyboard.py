"""Large-key on-screen keyboard for touchscreen kiosks and configuration dialogs."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)


class TouchKeyboardDialog(QDialog):
    def __init__(self, target=None, parent=None, numeric=False):
        super().__init__(parent)
        self.target = target
        self.numeric = numeric
        self.setWindowTitle("صفحه‌کلید لمسی")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(True)
        self.setMinimumWidth(620 if not numeric else 440)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)
        title = QLabel("ورودی را با کلیدهای لمسی وارد کنید")
        title.setObjectName("PageTitle")
        root.addWidget(title)
        grid = QGridLayout()
        grid.setSpacing(6)
        if numeric:
            rows = [
                list("۱۲۳۴۵۶۷۸۹۰"),
                list("٠١٢٣٤٥٦٧٨٩"),
            ]
        else:
            rows = [
                list("ضصثقفغعهخحجچ"),
                list("شسیبلاتنمکگ"),
                list("ظطزرذدپؤ"),
                list("abcdefghijklmnopqrstuvwxyz"),
                list("0123456789"),
            ]
        for row_index, keys in enumerate(rows):
            for col_index, key in enumerate(keys):
                button = QPushButton(key)
                button.setMinimumHeight(50)
                button.setMinimumWidth(42)
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                button.clicked.connect(lambda _checked=False, value=key: self._insert(value))
                grid.addWidget(button, row_index, col_index)
        root.addLayout(grid)
        actions = QHBoxLayout()
        for label, action in (
            ("فاصله", "space"),
            ("⌫ حذف", "backspace"),
            ("پاک‌کردن", "clear"),
            ("تمام", "done"),
        ):
            button = QPushButton(label)
            button.setMinimumHeight(50)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _checked=False, value=action: self._action(value))
            actions.addWidget(button)
        root.addLayout(actions)

    def _insert(self, text):
        if isinstance(self.target, QLineEdit):
            self.target.insert(text)
            self.target.setFocus()

    def _action(self, action):
        if action == "done":
            self.accept()
            return
        if not isinstance(self.target, QLineEdit):
            return
        if action == "space":
            self.target.insert(" ")
        elif action == "clear":
            self.target.clear()
        elif action == "backspace":
            cursor = self.target.cursorPosition()
            if self.target.hasSelectedText():
                self.target.insert("")
            elif cursor > 0:
                self.target.setSelection(cursor - 1, 1)
                self.target.insert("")
        self.target.setFocus()
