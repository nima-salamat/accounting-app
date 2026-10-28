"""Touch-friendly on-screen keyboard with staggered Persian and QWERTY layouts."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class TouchKeyboardDialog(QDialog):
    PERSIAN_ROWS = ("ضصثقفغعهخحجچ", "شسیبلاتنمکگ", "ظطزرذدپو")
    ENGLISH_ROWS = ("qwertyuiop[]", "asdfghjkl;'", "zxcvbnm,./")
    DIGITS_FA = "۱۲۳۴۵۶۷۸۹۰"
    DIGITS_EN = "1234567890"

    def __init__(self, target=None, parent=None, numeric=False):
        super().__init__(parent)
        self.target = target
        self.language = "fa"
        self.shifted = False
        self.symbols = bool(numeric)
        self.setWindowTitle("صفحه‌کلید لمسی")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setModal(True)
        self.setMinimumWidth(560 if numeric else 900)
        self.setMinimumHeight(330 if numeric else 440)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setStyleSheet("""
            QDialog { background:#151E2B; border:1px solid #344257; border-radius:16px; }
            QLabel { color:#E7EDF6; }
            QLabel#KeyboardTitle { font-size:16px; font-weight:800; padding:4px 8px; }
            QLabel#KeyboardHint { color:#9FB0C6; font-size:11px; padding:0 8px 4px; }
            QPushButton { color:#EAF0F8; background:#263447; border:1px solid #3A4A60;
                border-radius:8px; min-height:48px; min-width:36px; padding:4px 8px;
                font-size:18px; font-weight:650; }
            QPushButton:hover { background:#354961; border-color:#7CA8F1; }
            QPushButton:pressed { background:#4169A1; }
            QPushButton#KeyboardSpecial { background:#34445A; font-size:13px; min-width:66px; }
            QPushButton#KeyboardEnter { background:#315C9D; border-color:#4779BB; min-width:88px; }
            QPushButton#KeyboardSpace { min-width:260px; font-size:13px; }
            QPushButton#KeyboardClose { background:#1E2B3B; min-width:66px; font-size:13px; }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(8)
        heading = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("صفحه‌کلید لمسی")
        title.setObjectName("KeyboardTitle")
        hint = QLabel("چیدمان فارسی / QWERTY · کلیدهای بزرگ برای نمایشگر لمسی")
        hint.setObjectName("KeyboardHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        heading.addLayout(title_box, 1)
        self.language_button = self._special_button("EN", self.toggle_language)
        heading.addWidget(self.language_button)
        self.symbol_button = self._special_button("ABC" if self.symbols else "۱۲۳", self.toggle_symbols)
        heading.addWidget(self.symbol_button)
        self.close_button = self._special_button("تمام", self.accept)
        self.close_button.setObjectName("KeyboardClose")
        heading.addWidget(self.close_button)
        root.addLayout(heading)
        self.rows_host = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(7)
        root.addWidget(self.rows_host, 1)
        self._build_rows()

    def _special_button(self, label, callback):
        button = QPushButton(label)
        button.setObjectName("KeyboardSpecial")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(callback)
        return button

    def _key(self, label, value=None, width=None, kind="normal"):
        button = QPushButton(label)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setMinimumHeight(52)
        if width:
            button.setMinimumWidth(width)
        if kind == "special":
            button.setObjectName("KeyboardSpecial")
        elif kind == "enter":
            button.setObjectName("KeyboardEnter")
        elif kind == "space":
            button.setObjectName("KeyboardSpace")
        button.clicked.connect(lambda _checked=False, key=label if value is None else value: self._press(key))
        return button

    def _clear_rows(self):
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _add_row(self, keys, indent=0):
        container = QWidget()
        container.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        row = QHBoxLayout(container)
        row.setContentsMargins(indent, 0, 0, 0)
        row.setSpacing(5)
        for label, value, width, kind in keys:
            row.addWidget(self._key(label, value, width, kind))
        self.rows_layout.addWidget(container)

    @staticmethod
    def _key_spec(label, value=None, width=None, kind="normal"):
        return (label, value, width, kind)

    def _build_rows(self):
        self._clear_rows()
        digits = self.DIGITS_FA if self.language == "fa" else self.DIGITS_EN
        if self.symbols:
            self._add_row([self._key_spec(ch, ch) for ch in "~!@#$%^&*()"] + [
                self._key_spec("⌫ حذف", "backspace", 88, "special")
            ])
            self._add_row([self._key_spec(ch, ch) for ch in "-_=+[]{}"])
            self._add_row([self._key_spec(ch, ch) for ch in ";:,./<>?"])
            self._add_row([
                self._key_spec("ABC", "symbols", 78, "special"),
                self._key_spec("فاصله", "space", 290, "space"),
                self._key_spec("⏎ ورود", "enter", 96, "enter"),
            ], 44)
            return
        self._add_row([self._key_spec(ch, ch) for ch in digits] + [
            self._key_spec("-", "-"), self._key_spec("=", "="),
            self._key_spec("⌫ حذف", "backspace", 92, "special"),
        ])
        rows = self.PERSIAN_ROWS if self.language == "fa" else self.ENGLISH_ROWS
        self._add_row([
            self._key_spec(ch.upper() if self.shifted else ch, ch.upper() if self.shifted else ch)
            for ch in rows[0]
        ])
        self._add_row([
            self._key_spec(ch.upper() if self.shifted else ch, ch.upper() if self.shifted else ch)
            for ch in rows[1]
        ], 22)
        self._add_row([
            self._key_spec("⇧ Shift", "shift", 88, "special")
        ] + [
            self._key_spec(ch.upper() if self.shifted else ch, ch.upper() if self.shifted else ch)
            for ch in rows[2]
        ] + [
            self._key_spec("⌫", "backspace", 58, "special")
        ], 44)
        punct = ("،", ".", "؟") if self.language == "fa" else (",", ".", "?")
        self._add_row([
            self._key_spec("Tab ↹", "tab", 70, "special"),
            self._key_spec(punct[0], punct[0], 50),
            self._key_spec("فاصله", "space", 290, "space"),
            self._key_spec(punct[1], punct[1], 50),
            self._key_spec(punct[2], punct[2], 50),
            self._key_spec("⏎ ورود", "enter", 96, "enter"),
        ])

    def toggle_language(self):
        self.language = "en" if self.language == "fa" else "fa"
        self.language_button.setText("فا" if self.language == "en" else "EN")
        self._build_rows()

    def toggle_symbols(self):
        self.symbols = not self.symbols
        self.symbol_button.setText("ABC" if self.symbols else "۱۲۳")
        self._build_rows()

    def _press(self, value):
        target = self.target
        if not isinstance(target, QLineEdit):
            return
        if value == "shift":
            self.shifted = not self.shifted
            self._build_rows()
            return
        if value == "symbols":
            self.toggle_symbols()
            return
        if value == "enter":
            target.returnPressed.emit()
            self.accept()
            return
        if value == "tab":
            target.insert("\t")
        elif value == "space":
            target.insert(" ")
        elif value == "backspace":
            if target.hasSelectedText():
                start = target.selectionStart()
                target.setSelection(start, len(target.selectedText()))
                target.insert("")
            else:
                cursor = target.cursorPosition()
                if cursor > 0:
                    target.setSelection(cursor - 1, 1)
                    target.insert("")
        else:
            target.insert(str(value))
        if self.shifted:
            self.shifted = False
            self._build_rows()
