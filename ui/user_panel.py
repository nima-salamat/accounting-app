from ui.base_panel import TableManagement
from PySide2.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QMessageBox,
    QVBoxLayout, QHBoxLayout, QFormLayout, QSizePolicy, QFrame, QCheckBox
)
from PySide2.QtCore import Qt
from PySide2.QtGui import QFont
from peewee import IntegrityError
from db.models import User
from manager.db import DBManager
class UserManagement(TableManagement):
    
   

    def __init__(self, parent=None):
        super().__init__(parent,
                       display_fields=['username', "is_admin", 'created_at', "updated_at"],
                        create_fields=['username', 'password', "is_admin"],
                        searchable_fields=["username", "id","is_admin", "created_at"],
                        image_fields=[],
                        field_labels={
                            'username': 'نام کاربری',
                            'created_at': 'زمان ساخت',
                            'password': 'رمز عبور',
                            'updated_at': 'زمان آپدیت',
                            'is_admin': 'ادمین'
                        }
                         )
        self._parent = parent
        self.setModel(User)
        


from PySide2.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QMessageBox,
    QVBoxLayout, QHBoxLayout, QFormLayout, QCheckBox, QFrame, QToolButton, QStyle
)
from PySide2.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
from PySide2.QtCore import QSize, Qt
from peewee import IntegrityError

class PasswordLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.Password)
        self._eye_btn = QToolButton(self)
        self._eye_btn.setCursor(Qt.PointingHandCursor)
        self._eye_btn.setCheckable(True)
        self._eye_btn.setFixedSize(20, 20)
        self._eye_btn.setStyleSheet("border: none; padding: 0; background: transparent;")
        self._eye_btn.toggled.connect(self._on_eye_toggled)
        self._update_icon(False)
        self._update_position()
        self.textChanged.connect(self._update_position)
        self.resizeEvent = self._on_resize

    def _on_resize(self, event):
        self._update_position()
        super().resizeEvent(event)

    def _update_position(self):
        fw = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        x = self.rect().right() - fw - self._eye_btn.width() - 2
        y = (self.rect().bottom() - self._eye_btn.height()) // 2
        self._eye_btn.move(x, y)
        self.setStyleSheet(f"QLineEdit {{ padding-right: {self._eye_btn.width()+4}px; }}")

    def _on_eye_toggled(self, checked):
        self.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        self._update_icon(checked)

    def _update_icon(self, visible: bool):
        size = 16
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        c = Qt.black
        p.setPen(c)
        p.drawEllipse(2, 5, 12, 6)
        if visible:
            p.setBrush(c)
            p.drawEllipse(6, 7, 4, 2)
        p.end()
        self._eye_btn.setIcon(QIcon(pm))
        self._eye_btn.setIconSize(QSize(size, size))

class UserPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(700)
        self.setFont(QFont("Segoe UI", 10))

        header = QLabel("مدیریت کاربران", alignment=Qt.AlignCenter)
        header.setFixedHeight(30)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(20) 
        main_layout.addWidget(header)

        body = QHBoxLayout()
        body.setSpacing(24)
        body.addWidget(self.build_add_user_section())

        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        body.addWidget(divider)
        body.addWidget(self.build_change_password_section())

        main_layout.addLayout(body)

    def build_add_user_section(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20) 
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("افزودن کاربر جدید", alignment=Qt.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignLeft)
        form.setSpacing(12)         
        form.setVerticalSpacing(12)  
        form.setHorizontalSpacing(8) 

        self.inp_new_username = QLineEdit()
        self.inp_new_username.setPlaceholderText("نام کاربری حداقل ۴ کاراکتر")
        self.inp_new_username.setFixedWidth(260)

        self.inp_new_password = PasswordLineEdit()
        self.inp_new_password.setPlaceholderText("رمز عبور حداقل ۴ کاراکتر")
        self.inp_new_password.setFixedWidth(260)

        self.inp_confirm_password = PasswordLineEdit()
        self.inp_confirm_password.setPlaceholderText("تایید رمز عبور")
        self.inp_confirm_password.setFixedWidth(260)

        self.chk_is_admin = QCheckBox("مدیر")

        form.addRow(self.inp_new_username, QLabel("نام کاربری"))
        form.addRow(self.inp_new_password, QLabel("رمز عبور"))
        form.addRow(self.inp_confirm_password, QLabel("تایید رمز عبور"))
        form.addRow(self.chk_is_admin,        QLabel(""))

        self.lbl_add_error = QLabel()
        self.lbl_add_error.setVisible(False)

        self.btn_add_user = QPushButton("افزودن کاربر")
        self.btn_add_user.setFixedSize(120, 32)
        self.btn_add_user.clicked.connect(self.handle_add_user)

        layout.addLayout(form)
        layout.addWidget(self.lbl_add_error)
        layout.addWidget(self.btn_add_user, alignment=Qt.AlignCenter)
        return container

    def build_change_password_section(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("تغییر رمز عبور", alignment=Qt.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignLeft)
        form.setSpacing(12)
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(20)

        self.inp_existing_user = QLineEdit()
        self.inp_existing_user.setPlaceholderText("نام کاربری موجود")
        self.inp_existing_user.setFixedWidth(260)

        self.inp_new_pass = PasswordLineEdit()
        self.inp_new_pass.setPlaceholderText("رمز عبور جدید")
        self.inp_new_pass.setFixedWidth(260)

        self.inp_confirm_new = PasswordLineEdit()
        self.inp_confirm_new.setPlaceholderText("تایید رمز عبور جدید")
        self.inp_confirm_new.setFixedWidth(260)

        form.addRow(self.inp_existing_user, QLabel("نام کاربری"))
        form.addRow(self.inp_new_pass,       QLabel("رمز عبور جدید"))
        form.addRow(self.inp_confirm_new,    QLabel("تایید رمز عبور جدید"))

        self.lbl_change_error = QLabel()
        self.lbl_change_error.setVisible(False)

        self.btn_change_password = QPushButton("تغییر رمز عبور")
        self.btn_change_password.setFixedSize(120, 32)
        self.btn_change_password.clicked.connect(self.handle_change_password)

        layout.addLayout(form)
        layout.addWidget(self.lbl_change_error)
        layout.addWidget(self.btn_change_password, alignment=Qt.AlignCenter)
        return container

    def handle_add_user(self):
        username = self.inp_new_username.text().strip()
        password = self.inp_new_password.text().strip()
        confirm = self.inp_confirm_password.text().strip()
        is_admin = self.chk_is_admin.isChecked()
        self.lbl_add_error.setVisible(False)

        if not username or not password or not confirm:
            self.show_error(self.lbl_add_error, "ل لطفاً همهٔ فیلدها را پر کنید.")
            return
        if len(username) < 4 or len(password) < 4:
            self.show_error(self.lbl_add_error, "نام کاربری و رمز عبور باید حداقل ۴ کاراکتر باشند.")
            return
        if password != confirm:
            self.show_error(self.lbl_add_error, "رمزهای عبور مطابقت ندارند.")
            return

        try:
            with DBManager():
                user = User.create(username=username, password=password, is_admin=is_admin)
                user.set_password(password)
                user.save()
            QMessageBox.information(self, "موفقیت", f"کاربر «{username}» اضافه شد.")
            self.inp_new_username.clear()
            self.inp_new_password.clear()
            self.inp_confirm_password.clear()
            self.chk_is_admin.setChecked(False)
        except IntegrityError:
            self.show_error(self.lbl_add_error, "این نام کاربری قبلاً وجود دارد.")
        except Exception as e:
            self.show_error(self.lbl_add_error, f"خطا در افزودن کاربر:\n{str(e)}")

    def handle_change_password(self):
        username = self.inp_existing_user.text().strip()
        new_password = self.inp_new_pass.text().strip()
        confirm_password = self.inp_confirm_new.text().strip()
        self.lbl_change_error.setVisible(False)

        if not username or not new_password or not confirm_password:
            self.show_error(self.lbl_change_error, "لطفاً همهٔ فیلدها را پر کنید.")
            return
        if new_password != confirm_password:
            self.show_error(self.lbl_change_error, "رمزهای عبور مطابقت ندارند.")
            return

        try:
            with DBManager():
                user = User.get(User.username == username)
                user.set_password(new_password)
                user.save()
            QMessageBox.information(self, "موفقیت", f"رمز عبور «{username}» تغییر یافت.")
            self.inp_existing_user.clear()
            self.inp_new_pass.clear()
            self.inp_confirm_new.clear()
        except User.DoesNotExist:
            self.show_error(self.lbl_change_error, "کاربری یافت نشد.")
        except Exception as e:
            self.show_error(self.lbl_change_error, f"خطا در تغییر رمز عبور:\n{str(e)}")

    def show_error(self, label, msg):
        label.setText(msg)
        label.setVisible(True)
