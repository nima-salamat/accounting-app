# global
import weakref
from PySide2.QtCore import QThread

all_threads = []

class TrackingQThread(QThread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        all_threads.append(weakref.ref(self))
