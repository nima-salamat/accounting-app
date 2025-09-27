from PySide2.QtWidgets import (
    QMenuBar, QMenu, QSizePolicy, QMessageBox, QAction, QActionGroup, QLabel, QWidget, QHBoxLayout
)
from PySide2.QtCore import Qt, QTimer
import jdatetime


class MenuBar(QMenuBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent

        self.file = QMenu("&فایل")
        self.view = QMenu("&تنظیمات")
        self.help = QMenu("&درباره")

        self.addMenu(self.file)
        self.addMenu(self.view)
        self.addMenu(self.help)

        self.exit_action = QAction("&بستن")
        self.logout_action = QAction("&خروج(لاگ اوت)")
        self.more_settings = QAction("تنظیمات بیشتر")
        self.more_settings.triggered.connect(self.more_setting_pressed)
        
        self.about_action = QAction("&درباره")

        self.theme_toggle_action = QAction("تم تاریک")
        self.theme_toggle_action.setCheckable(True)
        self.theme_toggle_action.setChecked(self._parent._parent.mode == "dark")

        self.screensaver_group = QActionGroup(self)
        self.screensaver_group.setExclusive(True)

        self.clock_action = QAction("🕒 ساعت")
        self.clock_action.setCheckable(True)

        self.balls_action = QAction("🟢 توپ")
        self.balls_action.setCheckable(True)

        if self._parent._parent.screen_saver_mode == "clock":
            self.clock_action.setChecked(True)
        elif self._parent._parent.screen_saver_mode == "balls":
            self.balls_action.setChecked(True)
        else:
            self.clock_action.setChecked(True)

        self.screensaver_group.addAction(self.clock_action)
        self.screensaver_group.addAction(self.balls_action)

        self.file.addAction(self.logout_action)
        self.file.addAction(self.exit_action)

        self.view.addAction(self.theme_toggle_action)

        self.screensaver_menu = QMenu("اسکرین سیور")
        self.screensaver_menu.addAction(self.clock_action)
        self.screensaver_menu.addAction(self.balls_action)
        self.view.addMenu(self.screensaver_menu)
        
        

        self.help.addAction(self.about_action)
        self.calculator_action = QAction("ماشین‌حساب")
        self.view.addAction(self.calculator_action)
        self.calculator_action.triggered.connect(self.show_calculator)

        self.view.addAction(self.more_settings)
        self.logout_action.triggered.connect(self.logout_window)
        self.exit_action.triggered.connect(self.close_window)
        self.about_action.triggered.connect(self.show_about_box)
        self.theme_toggle_action.triggered.connect(self.toggle_theme)

        self.clock_action.triggered.connect(lambda: self.handle_screensaver_mode("clock"))
        self.balls_action.triggered.connect(lambda: self.handle_screensaver_mode("balls"))

        self.setFixedHeight(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.clock_label = QLabel(self)
        self.clock_label.setAlignment(Qt.AlignCenter)
        self.clock_label.setStyleSheet("padding-right: 12px; font-weight: 600; color: #AAA;")
       
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch() 
        layout.addWidget(self.clock_label)

        container.setFixedHeight(50)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        container.setParent(self)
        container.move(self.width() - container.width() - 20, 0)
        container.show()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()

        self.resizeEvent = self.on_resize

    def on_resize(self, event):
        container_width = self.clock_label.sizeHint().width() + 24  # padding + widget width
        self.clock_label.parentWidget().setGeometry(self.width() - container_width, 0, container_width, self.height())
        event.accept()

    def update_time(self):
        now = jdatetime.datetime.now()
        time_str = now.strftime("%Y/%m/%d - %H:%M:%S")
        self.clock_label.setText(time_str)


    def logout_window(self):
            print(self._parent._parent.page_stack)
            self._parent._parent.page_stack.setCurrentIndex(0)
            self._parent._parent.auth_page.update_theme(self._parent._parent.mode)
            
            self._parent._parent.auth_page.lbl_error.setText("")
            self._parent._parent.auth_page.inp_username.setText("")
            self._parent._parent.auth_page.inp_password.setText("")
            self._parent.manager_panel.show_page(0)
            
    def show_about_box(self):
        about_msg_box = QMessageBox()
        about_msg_box.setWindowTitle("درباره")
        about_msg_box.setText("کاری از انارتیم")
        about_msg_box.setInformativeText("done?!?!?!")
        about_msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)
        about_msg_box.exec_()

    def close_window(self):
        self._parent._parent.close()

    def toggle_theme(self, checked):
        if checked:
            self._parent._parent.mode = "dark"
            self._parent.update_theme("dark")
        else:
            self._parent._parent.mode = "light"
            self._parent.update_theme("light")

        self._parent._parent.save_keys()
        
    def handle_screensaver_mode(self, mode):
        self._parent._parent.set_screen_saver_mode(mode)
        self._parent._parent.save_keys()
    
    def show_calculator(self):
        if hasattr(self, 'calc_window') and self.calc_window is not None:
            self.calc_window.close()
            self.calc_window = None
        else:
            self.calc_window = Calculator(self._parent._parent)
            self.calc_window.resize(300, 400)
            self.calc_window.show()
            self.calc_window.move(100, 100)
            self.calc_window.raise_()

    def more_setting_pressed(self):
        self._parent._parent.page_stack.setCurrentIndex(3)
from PySide2.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QSizeGrip, QToolButton, QListWidget, QListWidgetItem, QFrame, QSizePolicy
)
from PySide2.QtCore import Qt
from functools import partial


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

    # ... other methods remain unchanged ...

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
            result = str(eval(expr))
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


