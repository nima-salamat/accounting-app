from PySide2.QtWidgets import (
    QWidget, QPushButton, QLabel, QHBoxLayout
)
from PySide2.QtCore import Qt, QTimer, QTime, QDateTime
import jdatetime


class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(36)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("TitleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

       
        self.title_label = QLabel("برنامه حسابداری ", self)
        layout.addWidget(self.title_label)

       
        self.clock_label = QLabel(self)
        self.clock_label.setAlignment(Qt.AlignCenter)
        layout.addStretch()
        layout.addWidget(self.clock_label)
        layout.addStretch()

       
        btn_min = QPushButton("➖", self)
        btn_min.setProperty("class", "flat")
        btn_min.clicked.connect(parent.showMinimized)
        layout.addWidget(btn_min)

      
        btn_close = QPushButton("❌", self)
        btn_close.setProperty("class", "flat")
        btn_close.clicked.connect(parent.close)
        layout.addWidget(btn_close)

        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()

    def update_time(self):
        now = jdatetime.datetime.now()
        time_str = now.strftime("%Y/%m/%d - %H:%M:%S")
        self.clock_label.setText(time_str)

    def update(self, mode):
        print(mode,"_")
        if mode == "dark":
            self.setStyleSheet("""
#TitleBar {
    background-color: #1E1E1E;
}
#TitleBar QLabel {
    color: #DDD;
    font-size: 14px;
    font-weight: 600;
}
#TitleBar QPushButton[class="flat"] {
        background-color: transparent;
    color: #AAA;
    border: none;
    padding: 0px 0px;
    font-size: 12px;
    font-weight: 500;
    padding: 4px;
    margin: 0px;
}
#TitleBar QPushButton[class="flat"]:hover {
    color: #80C0FF;
    background-color: rgba(128,192,255,0.15);
}
#TitleBar QPushButton[class="flat"]:pressed {
    color: #5A9BD8;
    background-color: rgba(128,192,255,0.25);
}
""")
        else:
            self.setStyleSheet("""
#TitleBar {
    background-color: #F5F5F5;
}
#TitleBar QLabel {
    color: #222;
    font-size: 14px;
    font-weight: 600;
}
#TitleBar QPushButton[class="flat"] {
        background-color: transparent;
    color: #AAA;
    border: none;
    padding: 0px 0px;
    font-size: 12px;
    font-weight: 500;
    padding: 4px;
    margin: 0px;
}
#TitleBar QPushButton[class="flat"]:hover {
    color: #3F51B5;
    background-color: rgba(63,81,181,0.15);
}
#TitleBar QPushButton[class="flat"]:pressed {
    color: #2A4A8A;
    background-color: rgba(63,81,181,0.25);
}
""")
