"""Frameless desktop calculator dialog with a local expression history."""
from functools import partial

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QLineEdit, QToolButton, QFrame, QSizeGrip, QListWidget, QListWidgetItem,
    QSizePolicy,
)
from PySide6.QtCore import Qt

from accounting_app.services.calculator import evaluate_expression


class Calculator(QWidget):
   
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("calculator_widget")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumSize(300, 400)
        self.resize(400, 450)

        self.drag_position = None
        self._build_ui()
        self._apply_styles()

    def _apply_styles(self):
        self.setStyleSheet("""
            #calculator_widget {
                background-color: #21222c;
                border: 1px solid #64676d;
                border-radius: 8px;
                color: #c5c8c6;
                font-family: 'Segoe UI', sans-serif;
            }
            QLineEdit#display {
                background-color: #282a36;
                color: #f8f8f2;
                font-size: 20px;
                padding: 5px;
                border: 1px solid #6272a4;
                border-radius: 4px;
            }
            QListWidget {
                background-color: #282a36;
                color: #f8f8f2;
                font-size: 12px;
                border: 1px solid #6272a4;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #44475a;
                border: none;
                color: #f8f8f2;
                font-size: 16px;
                padding: 6px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #6272a4;
            }
            QPushButton:pressed {
                background-color: #44475a;
            }
            QPushButton#btnClear {
                background-color: #ff5555;
            }
            QPushButton#btnClear:hover {
                background-color: #ff6e6e;
            }
            QToolButton#toggleHistoryBtn {
                background-color: transparent;
                color: #c5c8c6;
                font-size: 14px;
            }
            QToolButton#toggleHistoryBtn:hover {
                color: #6272a4;
            }
        """)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Title bar
        top_bar = QFrame(self)
        top_bar.setObjectName("top_bar")
        top_bar.setCursor(Qt.OpenHandCursor)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(6, 2, 6, 2)
        top_layout.setSpacing(4)

        self.title_label = QLabel("ماشین‌حساب", top_bar)
        self.title_label.setStyleSheet("font-size: 16px; color: #f8f8f2;")
        top_layout.addWidget(self.title_label)
        top_layout.addStretch()

        self.close_btn = QPushButton("✖", top_bar)
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self.close)
        top_layout.addWidget(self.close_btn)
        main_layout.addWidget(top_bar)

        # Display
        self.display = QLineEdit(self)
        self.display.setObjectName("display")
        self.display.setReadOnly(True)
        self.display.setMinimumHeight(40)
        main_layout.addWidget(self.display)

        # Toggle history
        toggle_layout = QHBoxLayout()
        toggle_layout.addStretch()
        self.toggle_history_btn = QToolButton(self)
        self.toggle_history_btn.setObjectName("toggleHistoryBtn")
        self.toggle_history_btn.setText("تاریخچه ▼")
        self.toggle_history_btn.setCheckable(True)
        self.toggle_history_btn.setChecked(True)
        self.toggle_history_btn.clicked.connect(self._toggle_history)
        toggle_layout.addWidget(self.toggle_history_btn)
        main_layout.addLayout(toggle_layout)

        # Buttons + history
        container = QHBoxLayout()
        container.setSpacing(6)

        # Button grid
        btn_frame = QFrame(self)
        btn_layout = QGridLayout(btn_frame)
        btn_layout.setSpacing(4)
        keys = [
            ('7','8','9','/'),
            ('4','5','6','*'),
            ('1','2','3','-'),
            ('0','.','C','+'),
            ('(',')','=','')
        ]
        for r, row in enumerate(keys):
            for c, key in enumerate(row):
                if not key:
                    continue
                btn = QPushButton(key, btn_frame)
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                btn.clicked.connect(partial(self._on_key, key))
                if key == 'C':
                    btn.setObjectName('btnClear')
                btn_layout.addWidget(btn, r, c)
        container.addWidget(btn_frame, 3)

        # History list
        self.history_list = QListWidget(self)
        self.history_list.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.history_list.setMinimumWidth(100)
        self.history_list.itemClicked.connect(self._on_history_click)
        container.addWidget(self.history_list, 1)

        main_layout.addLayout(container)

        # Resize grip
        grip = QSizeGrip(self)
        main_layout.addWidget(grip, alignment=Qt.AlignBottom | Qt.AlignRight)

        # Drag handlers
        top_bar.mousePressEvent = self._press
        top_bar.mouseMoveEvent = self._move


    def _toggle_history(self):
        if self.toggle_history_btn.isChecked():
            self.history_list.show()
            self.toggle_history_btn.setText("تاریخچه ▼")
        else:
            self.history_list.hide()
            self.toggle_history_btn.setText("تاریخچه ▶")

    def _press(self, e):
        if e.button() == Qt.LeftButton:
            self.drag_position = e.globalPos() - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)
            e.accept()

    def _move(self, e):
        if e.buttons() & Qt.LeftButton and getattr(self, 'drag_position', None):
            self.move(e.globalPos() - self.drag_position)
            e.accept()

    def mouseReleaseEvent(self, e):
        self.setCursor(Qt.ArrowCursor)
        self.drag_position = None
        super().mouseReleaseEvent(e)

    def _on_key(self, key):
        if key == 'C':
            self.display.clear()
        elif key == '=':
            expr = self.display.text().strip()
            if expr:
                self._evaluate(expr)
        else:
            self.display.setText(self.display.text() + key)

    def _evaluate(self, expr: str):
        try:
            result = str(evaluate_expression(expr))
        except Exception:
            result = "خطا"
        if result != "خطا":
            self.history_list.addItem(f"{expr} = {result}")
        self.display.setText(result)

    def _on_history_click(self, item: QListWidgetItem):
        text = item.text()
        if '=' in text:
            _, val = text.rsplit('=', 1)
            self.display.setText(val.strip())

    def insert_text(self, text: str):
        """Insert text programmatically"""
        self.display.setText(self.display.text() + text)
