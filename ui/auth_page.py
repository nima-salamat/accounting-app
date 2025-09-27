from PySide2.QtWidgets import (
    QWidget, QLineEdit, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QSizePolicy
)
from PySide2.QtCore import Qt, QEvent
from PySide2.QtGui import QPixmap
from config import USERNAME_MIN_LENGTH, PASSWORD_MIN_LENGTH


class FocusLabel(QLabel):
    def __init__(self, text, related_widget, *args, **kwargs):
        super().__init__(text, *args, **kwargs)
        self.related_widget = related_widget
        self.related_widget.installEventFilter(self)
        self.setProperty("focused", False)
        self.updateStyle()

    def eventFilter(self, obj, event):
        if obj is self.related_widget:
            if event.type() == QEvent.FocusIn:
                self.setProperty("focused", True)
                self.updateStyle()
            elif event.type() == QEvent.FocusOut:
                self.setProperty("focused", False)
                self.updateStyle()
        return super().eventFilter(obj, event)

    def updateStyle(self):
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class AuthPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent = parent
        self.original_pixmap = QPixmap("assets/cool-purple-background-design.jpg")

        self.main_h_layout = QHBoxLayout()
        self.main_h_layout.setContentsMargins(0, 0, 0, 0)
        self.main_h_layout.setSpacing(0)
        self.setLayout(self.main_h_layout)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setScaledContents(True)
        self.image_label.setPixmap(self.original_pixmap)
        self.image_label.setContentsMargins(0, 0, 0, 0)
        self.image_label.setMinimumHeight(0)
        self.image_label.setMaximumHeight(16777215)
        self.main_h_layout.addWidget(self.image_label, 1)

        self.form_container = QWidget()
        self.form_layout = QVBoxLayout()
        self.form_layout.setContentsMargins(50, 50, 50, 50)
        self.form_layout.setSpacing(20)
        self.form_container.setLayout(self.form_layout)
        self.main_h_layout.addWidget(self.form_container, 1)

        self.welcome_message = QLabel("")
        self.welcome_message.setWordWrap(True)
        self.welcome_message.setObjectName("welcome_label")
        self.welcome_message.setLayoutDirection(Qt.RightToLeft) 
        self.welcome_message.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)  
        self.form_layout.addWidget(self.welcome_message)


        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("error_label")
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setVisible(False)
        self.form_layout.addWidget(self.lbl_error)

        self.username_layout = QHBoxLayout()
        self.username_layout.addSpacing(20)
        self.inp_username = QLineEdit()
        self.inp_username.setPlaceholderText("نام کاربری را وارد کنید")
        self.inp_username.setMinimumHeight(46)
        self.lbl_username = FocusLabel("نام کاربری", self.inp_username)
        
        self.username_layout.addWidget(self.lbl_username)
        self.username_layout.addWidget(self.inp_username)
        self.form_layout.addLayout(self.username_layout)

        self.password_layout = QHBoxLayout()
        self.password_layout.addSpacing(20)
        self.inp_password = QLineEdit()
        self.inp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_password.setPlaceholderText("رمز عبور را وارد کنید")
        self.inp_password.setMinimumHeight(46)
        self.lbl_password = FocusLabel("رمزعبور", self.inp_password)
        self.password_layout.addWidget(self.lbl_password)
        self.password_layout.addWidget(self.inp_password)
        self.form_layout.addLayout(self.password_layout)

        self.login_layout = QHBoxLayout()
        self.login_layout.addStretch()
        self.btn_login = QPushButton("وارد شدن")
        self.btn_login.setObjectName("login_button")
        self.btn_login.setDefault(True)
        self.login_layout.addWidget(self.btn_login)

        self.btn_close = QPushButton("بستن")
        self.btn_close.setObjectName("close_button")
        self.login_layout.addWidget(self.btn_close)
        self.form_layout.addLayout(self.login_layout)

        self.btn_login.setFixedHeight(46)
        self.btn_close.setFixedHeight(46)
        self.btn_login.clicked.connect(self.handleLogin)
        self.btn_close.clicked.connect(self.handleClose)

        for widget in (
            self.welcome_message,
            self.lbl_username,
            self.inp_username,
            self.lbl_password,
            self.inp_password,
            self.lbl_error,
        ):
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMaximumWidth(350)
            widget.setMinimumWidth(250)

        self.lbl_error.setMaximumWidth(1000)

        self.update_theme(self._parent.mode)
        

    def update_theme(self, mode):
        if mode == "dark":
            self.setStyleSheet("""
            * {
                font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            }
            QWidget {
                background-color: #1E1E1E;
                margin: 0px;
                padding: 0px;
            }
            QLabel#welcome_label {
                font-size: 22px;
                font-weight: 700;
                margin-bottom: 20px;
                color: #fff;
                transition: all 0.25s ease;
            }
            QLabel#welcome_label:hover {
                color: #80c0ff;
                font-size: 26px;
                text-shadow: 0 0 12px #80c0ffaa;
            }
            QLabel#error_label {
                background-color: #e74c3c;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: 600;
                color: white;
                margin-top: 15px;
                box-shadow: 0 3px 7px rgba(0,0,0,0.4);
            }
            QLineEdit {
                background-color: #2A2A2A;
                color: #fff;
                border: 2px solid #555;
                border-radius: 14px;
                padding: 14px 20px;
                font-size: 17px;
                selection-background-color: #3f51b5;
                selection-color: white;
                transition: border-color 0.3s ease, background-color 0.3s ease;
            }
            QLineEdit::placeholder {
                color: #aaa;
            }
            QLineEdit:focus {
                border-color: #3f51b5;
                box-shadow: 0 0 6px #3f51b5aa;
            }
            QPushButton#login_button {
                background-color: #3f51b5;
                color: white;
                font-weight: 700;
                border-radius: 18px;
                padding: 14px 32px;
                min-width: 110px;
                min-height: 48px;
                box-shadow: 0 5px 16px rgba(63,81,181,0.6);
                transition: background-color 0.3s ease, box-shadow 0.3s ease;
            }
            QPushButton#login_button:hover {
                background-color: #2c387e;
                box-shadow: 0 8px 28px rgba(44,56,126,0.8);
            }
            QPushButton#close_button {
                background-color: #555;
                color: #ddd;
                font-weight: 600;
                border-radius: 18px;
                padding: 14px 28px;
                min-width: 100px;
                min-height: 48px;
                box-shadow: none;
                transition: background-color 0.3s ease;
            }
            QPushButton#close_button:hover {
                background-color: #777;
            }
            QLabel[focused="true"] {
                font-size: 19px;
                color: #80c0ff;
                font-weight: 700;
                text-shadow: 0 0 8px #80c0ffcc;
                transition: all 0.3s ease;
            }
            QLabel {
                font-weight: 600;
                min-width: 90px;
                color: #ddd;
                transition: all 0.3s ease;
            }
        """)
            
        elif mode == "light":
            self.setStyleSheet("""
            * {
                font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            }
            QWidget {
                background-color: #f5f5f5;
                margin: 0px;
                padding: 0px;
            }
            QLabel#welcome_label {
                font-size: 32px;
                font-weight: 700;
                margin-bottom: 20px;
                color: #222;
                transition: all 0.25s ease;
            }
            QLabel#welcome_label:hover {
                color: #3f51b5;
                font-size: 36px;
                text-shadow: 0 0 10px #3f51b544;
            }
            QLabel#error_label {
                background-color: #e74c3c;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: 600;
                color: white;
                margin-top: 15px;
                box-shadow: 0 3px 7px rgba(0,0,0,0.3);
            }
            QLineEdit {
                background-color: #ffffff;
                color: #222;
                border: 2px solid #aaa;
                border-radius: 14px;
                padding: 14px 20px;
                font-size: 17px;
                selection-background-color: #3f51b5;
                selection-color: white;
                transition: border-color 0.3s ease, background-color 0.3s ease;
            }
            QLineEdit::placeholder {
                color: #999;
            }
            QLineEdit:focus {
                border-color: #3f51b5;
                box-shadow: 0 0 6px #3f51b5aa;
            }
            QPushButton#login_button {
                background-color: #3f51b5;
                color: white;
                font-weight: 700;
                border-radius: 18px;
                padding: 14px 32px;
                min-width: 110px;
                min-height: 48px;
                box-shadow: 0 5px 16px rgba(63,81,181,0.4);
                transition: background-color 0.3s ease, box-shadow 0.3s ease;
            }
            QPushButton#login_button:hover {
                background-color: #2c387e;
                box-shadow: 0 8px 28px rgba(44,56,126,0.6);
            }
            QPushButton#close_button {
                background-color: #bbb;
                color: #333;
                font-weight: 600;
                border-radius: 18px;
                padding: 14px 28px;
                min-width: 100px;
                min-height: 48px;
                box-shadow: none;
                transition: background-color 0.3s ease;
            }
            QPushButton#close_button:hover {
                background-color: #999;
            }
            QLabel[focused="true"] {
                font-size: 19px;
                color: #3f51b5;
                font-weight: 700;
                text-shadow: 0 0 8px #3f51b566;
                transition: all 0.3s ease;
            }
            QLabel {
                font-weight: 600;
                min-width: 90px;
                color: #222;
                transition: all 0.3s ease;
            }
        """)

            
    def handleLogin(self):
        self._parent.AUTH_MANAGER = self._parent.AuthManager()
        username = self.inp_username.text().strip()
        password = self.inp_password.text().strip()
        if len(username) >= USERNAME_MIN_LENGTH and len(password) >= PASSWORD_MIN_LENGTH:
            self._parent.AUTH_MANAGER.validate(username, password)
            if self._parent.AUTH_MANAGER.is_authenticated():
                self.lbl_error.setVisible(False)
                self._parent.page_stack.setCurrentIndex(1)
                if self._parent.AUTH_MANAGER.user.is_admin:
                    self._parent.visible_buttons = [0,1,2,3,4,5,6,7,8,9,10, 11]
                    
                else:
                    self._parent.visible_buttons = [0,8]
                    
                self._parent.panel_page.manager_panel.set_visible_buttons(self._parent.visible_buttons)
                self._parent.load_keys()
                self._parent.panel_page.dock_widget.add_buttons_from_indices(self._parent.button_indices)
                self._parent.panel_page.manager_panel.show_page(0)
                
            
                self._parent.panel_page.manager_panel.page_stack.widget(0).card_visibility(self._parent.AUTH_MANAGER.user.is_admin) 
            else:
                self.lbl_error.setText(self._parent.AUTH_MANAGER.errors[-1])
                self.lbl_error.setVisible(True)
        else:
            self.lbl_error.setText("username and password length should be at least 4 chars.")
            self.lbl_error.setVisible(True)

    def handleClose(self):
        self._parent.close()