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

from ui.widgets.calculator_dialog import Calculator
