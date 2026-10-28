from PySide6.QtWidgets import (
    QWidget, QLineEdit, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QSizePolicy
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QPixmap
from config import USERNAME_MIN_LENGTH, PASSWORD_MIN_LENGTH
from ui.styles.auth_styles import AUTH_DARK_QSS, AUTH_LIGHT_QSS


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
            self.setStyleSheet(AUTH_DARK_QSS)
        elif mode == "light":
            self.setStyleSheet(AUTH_LIGHT_QSS)

    def handleLogin(self):
        self._parent.AUTH_MANAGER = self._parent.AuthManager()
        username = self.inp_username.text().strip()
        password = self.inp_password.text()
        if len(username) >= USERNAME_MIN_LENGTH and len(password) >= PASSWORD_MIN_LENGTH:
            self._parent.AUTH_MANAGER.validate(username, password)
            if self._parent.AUTH_MANAGER.is_authenticated():
                self.lbl_error.setVisible(False)
                self._parent.page_stack.setCurrentIndex(1)
                if self._parent.AUTH_MANAGER.user.is_admin:
                    self._parent.visible_buttons = [0,1,2,3,4,5,6,7,8,9,10,11,12]
                    
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
            self.lbl_error.setText("نام کاربری و رمز عبور باید حداقل ۴ نویسه داشته باشند.")
            self.lbl_error.setVisible(True)

    def handleClose(self):
        self._parent.close()