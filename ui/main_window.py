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
        self.installEventFilter(self)

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
        super().closeEvent(event)


    def save_keys(self):
        class Worker(QObject):
            finished = Signal()
            error = Signal(str)

            def run(self_inner):
                try:
                    if not isinstance(self.AUTH_MANAGER.user, AnonymousUser):
                        print("okey")
                        self.AUTH_MANAGER.user.buttons = json.dumps(self.button_indices)
                        self.AUTH_MANAGER.user.save()
                except: 
                    pass    
                try:
                    keys = {
                        "mode": self.mode,
                        "screen_saver_mode": self.screen_saver_mode,
                        "DISABLE_ANIMATIONS": self.DISABLE_ANIMATIONS,
                        "SHOW_PRODUCT_IMAGES": self.SHOW_PRODUCT_IMAGES,
                        
                    }
                    
                    with open(path_keys, "w") as f:
                        f.write(json.dumps(keys))
                    self_inner.finished.emit()
                except Exception as e:
                    self_inner.error.emit(str(e))

        self.thread = QThread()
        self.worker = Worker()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.worker.error.connect(lambda err: print(f"Error saving keys: {err}"))

        self.thread.start()

    def load_keys(self):
        if not os.path.exists(path_keys):
            with open(path_keys, "w"):
                pass
            return
        with open(path_keys, "r") as f:
            try: 
                keys = json.loads(f.read())
            except: 
                return 
            if keys.get("mode") is not None:
                self.mode = keys["mode"]
            if keys.get("screan_saver_mode") is not None:
                self.screen_saver_mode = keys["screen_saver_mode"]
            if keys.get("DISABLE_ANIMATIONS") is not None:
                self.DISABLE_ANIMATIONS = keys["DISABLE_ANIMATIONS"]
            if keys.get("SHOW_PRODUCT_IMAGES") is not None:
                self.SHOW_PRODUCT_IMAGES = keys["SHOW_PRODUCT_IMAGES"]
            if not isinstance(self.AUTH_MANAGER.user, AnonymousUser):
                if self.AUTH_MANAGER.user.buttons != "":
                    try:
                        self.button_indices = json.loads(self.AUTH_MANAGER.user.buttons)       
                        print(self.button_indices)             
                    except:
                        pass

    