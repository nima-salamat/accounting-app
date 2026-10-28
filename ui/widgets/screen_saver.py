# screen_savers.py

import random
from PySide2.QtCore import QTimer, QPointF, Qt, QTime
from PySide2.QtGui import QPainter, QColor, QFont
from PySide2.QtWidgets import QFrame

# -------------------------------------------------------------------
# QSS Definitions
# -------------------------------------------------------------------
dark_qss = """
QFrame {
    background-color: #121212;
    border: none;
}
"""

light_qss = """
QFrame {
    background-color: #f0f0f0;
    border: none;
}
"""

# -------------------------------------------------------------------
# Helper: Animated Circle
# -------------------------------------------------------------------
class Circle:
    def __init__(self, parent_width: int, parent_height: int):
        self.reset(parent_width, parent_height)

    def reset(self, parent_width: int, parent_height: int):
        """Reinitialize circle with random size, position and color."""
        self.radius = random.randint(20, 80)
        self.pos = QPointF(
            random.uniform(0, max(parent_width - self.radius, 1)),
            random.uniform(0, max(parent_height - self.radius, 1)),
        )
        self.color = QColor(
            random.randint(100, 255),
            random.randint(100, 255),
            random.randint(100, 255)
        )
        self.opacity = 0.0
        self.fade_in = True


# -------------------------------------------------------------------
# ScreenSaver: Animated fading circles
# -------------------------------------------------------------------
class ScreenSaver(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        # اجازه بده QSS پس‌زمینه را بر عهده بگیرد
        self.setAttribute(Qt.WA_StyledBackground, True)
        # ماوس از طریق این ویجت نشت پیدا کند
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        # لیست دایره‌ها را پس از ساخته شدن ویجت مقداردهی می‌کنیم
        QTimer.singleShot(0, self.init_circles)

        # تایمر به‌روزرسانی انیمیشن
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update_circles)
        self._timer.start(50)

        # حالت اولیه تم
        self.update_theme("dark")

    def init_circles(self):
        """Create initial set of circles."""
        self._circles = [Circle(self.width(), self.height()) for _ in range(10)]

    def resizeEvent(self, event):
        """Reset all circles to fit the new size."""
        for c in self._circles:
            c.reset(self.width(), self.height())
        super().resizeEvent(event)

    def update_circles(self):
        """Fade in/out circles and reset when opacity reaches 0."""
        for c in self._circles:
            if c.fade_in:
                c.opacity = min(c.opacity + 0.03, 1.0)
                if c.opacity >= 1.0:
                    c.fade_in = False
            else:
                c.opacity = max(c.opacity - 0.03, 0.0)
                if c.opacity <= 0.0:
                    c.reset(self.width(), self.height())
                    c.fade_in = True
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for c in self._circles:
            painter.setOpacity(c.opacity)
            painter.setBrush(c.color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(c.pos, c.radius, c.radius)

    def update_theme(self, mode: str):
        """Apply dark or light QSS to the frame background."""
        if mode == "dark":
            self.setStyleSheet(dark_qss)
        else:
            self.setStyleSheet(light_qss)
        self.update()


# -------------------------------------------------------------------
# ClockScreenSaver: Digital clock
# -------------------------------------------------------------------
class ClockScreenSaver(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        # اجازه بده QSS پس‌زمینه را بر عهده بگیرد
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        # قلم و رنگ متن
        self._font = QFont("Consolas", 72, QFont.Bold)
        self._color = QColor("#00FFAA")
        self._current_time = QTime.currentTime()

        # تایمر به‌روزرسانی ثانیه‌شمار
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update_time)
        self._timer.start(1000)

        # حالت اولیه تم
        self.update_theme("dark")

    def update_time(self):
        """Grab current time and trigger repaint."""
        self._current_time = QTime.currentTime()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font)
        painter.setPen(self._color)

        time_str = self._current_time.toString("HH:mm:ss")
        text_rect = painter.boundingRect(self.rect(), Qt.AlignCenter, time_str)
        painter.drawText(text_rect, Qt.AlignCenter, time_str)

    def update_theme(self, mode: str):
        """Apply dark or light QSS and adjust clock color/size."""
        if mode == "dark":
            self.setStyleSheet(dark_qss)
            self._color = QColor("#00FFAA")
            self._font.setPointSize(72)
        else:
            self.setStyleSheet(light_qss)
            self._color = QColor("#007ACC")
            self._font.setPointSize(68)
        self.update()
