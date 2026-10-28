from PySide2.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout, QStackedWidget, QStyle, QApplication
)
from PySide2.QtGui import QIcon, QMouseEvent, QFont
from PySide2.QtCore import Qt, QTimer, QEvent, QObject, Signal
from ui.auth_page import AuthPage
from ui.dashboard import MainPanel
from ui.screen_saver import ScreenSaver, ClockScreenSaver
from manager.auth import AuthManager, AnonymousUser
from config import keys_path
import json 
import os
from ui.thread import all_threads, TrackingQThread
from accounting_app.services.settings_store import load_settings, save_settings
from manager.db import DBManager
path_keys = keys_path
QThread = TrackingQThread

class MainWindow(QMainWindow):
    DISABLE_ANIMATIONS = False
    AuthManager = AuthManager
    SHOW_PRODUCT_IMAGES = True
    def __init__(self, parent=None):
        super().__init__(parent)
        self.AUTH_MANAGER = AuthManager()
        self.mode = "dark"
        self.screen_saver_mode = "clock"
        self.font_scale = 1.0

        self.button_indices = []
        self.visible_buttons = []
        self.visible_emojies = []
        self.load_keys() 
        
        # self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("برنامه حسابداری ")

        central = QWidget(self)
        vbox = QVBoxLayout(central)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)


        self.page_stack = QStackedWidget()
        vbox.addWidget(self.page_stack)

        self.auth_page = AuthPage(self)
        self.panel_page = MainPanel(self)
        self.screen_saver = ClockScreenSaver(self) if self.screen_saver_mode == "clock" else ScreenSaver(self)

        for p in (self.auth_page, self.panel_page, self.screen_saver):
            self.page_stack.addWidget(p)
        self.page_stack.setCurrentIndex(0)

        self._idle = 0
        self._prev = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_idle)
        self._timer.start(1000)
        application = QApplication.instance()
        if application is not None:
            # Filter child-widget input too, so activity resets the idle timer.
            application.installEventFilter(self)

        self.setCentralWidget(central)

        self.showMaximized()

    def _check_idle(self):
        self._idle += 1
        cur = self.page_stack.currentIndex()
        if self._idle >= 600 and cur != 2:
            self._prev = cur
            widget = self.page_stack.widget(2)

            self.page_stack.widget(2).update_theme(self.mode)
            
            self.page_stack.setCurrentIndex(2)
            

    def eventFilter(self, obj, event):
        if event.type() in (
            QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.KeyPress,
            QEvent.Wheel, QEvent.TouchBegin, QEvent.HoverMove
        ):
            self._idle = 0
            if self.page_stack.currentIndex() == 2:
                self.page_stack.setCurrentIndex(self._prev)
        return super().eventFilter(obj, event)

    def set_screen_saver_mode(self, mode: str):
        mode = mode if mode in ("clock", "balls") else "clock"
        self.screen_saver_mode = mode
        self.page_stack.removeWidget(self.screen_saver)
        self.screen_saver.deleteLater()
        self.screen_saver = ClockScreenSaver(self) if mode == "clock" else ScreenSaver(self)
        self.page_stack.addWidget(self.screen_saver)
    
    def closeEvent(self, event):
        for ref in all_threads:
            thread = ref()
            if thread is not None:
                try:
                    if thread.isRunning():
                        thread.quit()
                        thread.wait()
                except RuntimeError:
                    pass
        application = QApplication.instance()
        if application is not None:
            application.removeEventFilter(self)
        super().closeEvent(event)


    def save_keys(self):
        class Worker(QObject):
            finished = Signal()
            error = Signal(str)

            def run(self_inner):
                errors = []
                if not isinstance(self.AUTH_MANAGER.user, AnonymousUser):
                    try:
                        with DBManager():
                            self.AUTH_MANAGER.user.buttons = json.dumps(self.button_indices, ensure_ascii=False)
                            self.AUTH_MANAGER.user.save()
                    except Exception as exc:
                        errors.append("ذخیره تنظیمات کاربر ناموفق بود: {}".format(exc))
                settings = {
                    "mode": self.mode,
                    "screen_saver_mode": self.screen_saver_mode,
                    "DISABLE_ANIMATIONS": bool(self.DISABLE_ANIMATIONS),
                    "SHOW_PRODUCT_IMAGES": bool(self.SHOW_PRODUCT_IMAGES),
                }
                try:
                    save_settings(path_keys, settings)
                except Exception as exc:
                    errors.append("ذخیره تنظیمات برنامه ناموفق بود: {}".format(exc))
                if errors:
                    self_inner.error.emit("\n".join(errors))
                else:
                    self_inner.finished.emit()

        self.thread = QThread()
        self.worker = Worker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.thread.quit)
        self.worker.error.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.error.connect(lambda err: print("Settings save error: {}".format(err)))
        self.thread.start()

    def load_keys(self):
        settings = load_settings(path_keys)
        mode = settings.get("mode")
        if mode in ("dark", "light"):
            self.mode = mode
        # Accept the misspelled key emitted by older releases.
        saver_mode = settings.get("screen_saver_mode", settings.get("screan_saver_mode"))
        if saver_mode in ("clock", "balls"):
            self.screen_saver_mode = saver_mode
        disable_animations = settings.get("DISABLE_ANIMATIONS")
        if isinstance(disable_animations, bool):
            self.DISABLE_ANIMATIONS = disable_animations
        show_images = settings.get("SHOW_PRODUCT_IMAGES")
        if isinstance(show_images, bool):
            self.SHOW_PRODUCT_IMAGES = show_images
        if not isinstance(self.AUTH_MANAGER.user, AnonymousUser):
            stored_buttons = self.AUTH_MANAGER.user.buttons
            if stored_buttons:
                try:
                    buttons = json.loads(stored_buttons)
                    if isinstance(buttons, list):
                        self.button_indices = [
                            value for value in buttons
                            if type(value) is int and 0 <= value < 13
                        ]
                except (TypeError, ValueError):
                    self.button_indices = []
