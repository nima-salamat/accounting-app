from ui.base_panel import TableManagement
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QMessageBox,
    QVBoxLayout, QHBoxLayout, QFormLayout, QFrame, QCheckBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from ui.widgets.password_line_edit import PasswordLineEdit
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
        password = self.inp_new_password.text()
        confirm = self.inp_confirm_password.text()
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
                user = User(username=username, password="", is_admin=is_admin)
                user.set_password(password)
                user.save(force_insert=True)
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
        new_password = self.inp_new_pass.text()
        confirm_password = self.inp_confirm_new.text()
        self.lbl_change_error.setVisible(False)

        if not username or not new_password or not confirm_password:
            self.show_error(self.lbl_change_error, "لطفاً همهٔ فیلدها را پر کنید.")
            return
        if len(new_password) < 4:
            self.show_error(self.lbl_change_error, "رمز عبور باید حداقل ۴ نویسه داشته باشد.")
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
