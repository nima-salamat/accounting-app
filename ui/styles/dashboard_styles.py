dark_qss = """
* {
    font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
    font-size: 14px;
    outline: none;
}

QWidget {
    background-color: #1E1E1E;
    color: #DDD;
}

#page_stack {
      background-color: rgba(30, 30, 30, 150);
    border-radius: 16px;
    margin: 5px;

    border-radius: 16px;
}
.my_panel {
    background-color: rgba(240, 240, 240, 200);
    border-radius: 12px;
}

#button_container, QWidget#button_container {
    background-color: transparent;
}

/* ===== ToggleButton ===== */
#ToggleButton {
    background-color: transparent;
    color: white;
    border: none;
    min-width: 20px;
    max-width: 20px;
    width: 20px;
}
#ToggleButton:hover {
    background-color: #3c3c3c;
}

/* ===== QLabel ===== */
QLabel {
    color: #CCC;
    font-weight: 600;
}
QLabel:hover {
    color: #80C0FF;
}
QLabel[focused="true"] {
    color: #80C0FF;
    font-size: 16px;
    font-weight: 700;
}

/* ===== QLineEdit ===== */
QLineEdit {
    background-color: #2A2A2A;
    color: #EEE;
    border: 1.5px solid #444;
    border-radius: 8px;
    padding: 8px 12px;
}
QLineEdit::placeholder {
    color: #888;
}
QLineEdit:focus {
    border-color: #3F51B5;
    background-color: #303030;
}

/* ===== QPushButton ===== */
QPushButton {
    background-color: #3F51B5;
    color: white;
    border-radius: 6px;
    padding: 8px 18px;
    min-width: 70px;
    min-height: 34px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #2C387E;
}
QPushButton:pressed {
    background-color: #1E2B5A;
}
QTableCornerButton::section {
    background-color: #2c2c2c;
    border: none;
}


/* ===== QPushButton Flat ===== */
QPushButton[class="flat"] {
    background-color: transparent;
    color: #AAA;
    border: none;
    padding: 0px 0px;
    font-size: 12px;
    font-weight: 500;
}
QPushButton[class="flat"]:hover {
    color: #80C0FF;
    background-color: rgba(128, 192, 255, 0.15);
}
QPushButton[class="flat"]:pressed {
    background-color: rgba(128, 192, 255, 0.25);
    color: #5A9BD8;
}

/* ===== ScrollBars ===== */
QScrollBar:vertical, QScrollBar:horizontal {
    background: #1E1E1E;
    width: 12px;
    height: 12px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #444;
    border-radius: 6px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #666;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* ===== QTableWidget ===== */
QTableWidget {
    background-color: #2A2A2A;
    border: 1px solid #555;
    color: #EEE;
    selection-background-color: #3F51B5;
}

/* ===== QMenuBar and QMenu ===== */
QMenuBar {
    background-color: rgba(30, 30, 30, 150);
    color: #CCC;
    font-weight: 600;
}
QMenuBar::item {
    padding: 10px 18px;
}
QMenuBar::item:selected {
    background-color: #3F51B5;
    color: white;
}
QMenu {
    background-color: rgba(30, 30, 30, 150);
    color: #DDD;
    border: 1px solid #444;
    border-radius: 6px;
}
QMenu::item {
    padding: 8px 24px;
}
QMenu::item:selected {
    background-color: #3F51B5;
    color: white;
}
#TitleBar {
    background-color: #1E1E1E;
}


QSplitter::handle {
    background-color: #444;
    border: none;
    width: 4px; 
    height: 4px; 
}
QSplitter::handle:hover {
    background-color: #666;
}


QHeaderView::section {
    background-color: #444;
    color: #EEE; 
    padding: 4px;
    border: 1px solid #555;
    font-weight: bold;
}


QTabWidget::pane {
    border: 1px solid #444;
    border-radius: 10px;
    background: #2A2A2A;
}

QTabBar::tab {
    background: #444;
    color: #CCC;
    padding: 8px 16px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 2px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background: #3F51B5;
    color: white;
}

QTabBar::tab:hover {
    background: #5A6FC8;
    color: white;
}

QTabBar::tab:!selected {
    margin-top: 4px; 
}

QPushButton[active="true"] {
    background-color: #4466aa; 
    color: white;
    font-weight: bold;
    border: 2px solid #88aaff;
    border-radius: 6px;
}



"""


light_qss = """
/* ===== Global ===== */

QPushButton[active="true"] {
    background-color: #4466aa; 
    font-weight: bold;
    border: 2px solid #88aaff;
    border-radius: 6px;
}

DraggableButton[active="true"] {
    background-color: #2a80d4;
    color: white;
    font-weight: bold;
    border-radius: 5px;
}


QTabWidget::pane {
    border: 1px solid #CCC;
    border-radius: 10px;
    background: #FFF;
}

QTabBar::tab {
    background: #EEE;
    color: #333;
    padding: 8px 16px;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    margin-right: 2px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background: #3F51B5;
    color: white;
}

QTabBar::tab:hover {
    background: #5A6FC8;
    color: white;
}

QTabBar::tab:!selected {
    margin-top: 4px;
}



QHeaderView::section {
    background-color: #DDD;
    color: #222;
    padding: 4px;
    border: 1px solid #CCC;
    font-weight: bold;
}



* {
    font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
    font-size: 14px;
    outline: none;
}

#TitleBar {
    background-color: #F5F5F5;
}

QWidget {
    background-color: #F5F5F5;
    color: #222;
}

QSplitter::handle {
    background-color: #ccc;
    border: none;
    width: 4px;
    height: 4px;
}
QSplitter::handle:hover {
    background-color: #aaa;
}


#page_stack {
    background-color: rgba(255, 255, 255, 150);
    border-radius: 16px;
}

.my_panel {
    background-color: rgba(240, 240, 240, 200);
    border-radius: 12px;
}


#button_container, QWidget#button_container {
    background-color: transparent;  
}

/* ===== ToggleButton ===== */
#ToggleButton {
    background-color: transparent;
    color: black;
    border: none;
    min-width: 20px;
    max-width: 20px;
    width: 20px;
}
#ToggleButton:hover {
    background-color: rgba(0,0,0,0.05);
}

/* ===== QLabel ===== */
QLabel {
    color: #222;
    font-weight: 600;
}
QLabel:hover {
    color: #3F51B5;
}
QLabel[focused="true"] {
    color: #3F51B5;
    font-size: 16px;
    font-weight: 700;
}

/* ===== QLineEdit ===== */
QLineEdit {
    background-color: #FFF;
    color: #222;
    border: 1.5px solid #CCC;
    border-radius: 8px;
    padding: 8px 12px;
}
QLineEdit::placeholder {
    color: #888;
}
QLineEdit:focus {
    border-color: #3F51B5;
}

/* ===== QPushButton ===== */
QPushButton {
    background-color: #3F51B5;
    color: white;
    border-radius: 6px;
    padding: 8px 18px;
    min-width: 70px;
    min-height: 34px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #2C387E;
}
QPushButton:pressed {
    background-color: #1E2B5A;
}

/* ===== QPushButton Flat ===== */
QPushButton[class="flat"] {
    background-color: transparent;
    color: #555;
    border: none;
    padding: 1px 1px;
    font-size: 12px;
    font-weight: 500;
}
QPushButton[class="flat"]:hover {
    color: #3F51B5;
    background-color: rgba(63,81,181,0.15);
}
QPushButton[class="flat"]:pressed {
    background-color: rgba(63,81,181,0.25);
    color: #2A4A8A;
}

/* ===== ScrollBars ===== */
QScrollBar:vertical, QScrollBar:horizontal {
    background: #F4F4F4;
    width: 12px;
    height: 12px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #BBB;
    border-radius: 6px;
}
QScrollBar::handle:hover {
    background: #999;
}

/* ===== QTableWidget ===== */
QTableWidget {
    background-color: #FFF;
    border: 1px solid #CCC;
    color: #222;
    selection-background-color: #3F51B5;
}

/* ===== QMenuBar and QMenu ===== */
QMenuBar {
    background-color: rgba(245, 245, 245, 150);
    color: #222;
    font-weight: 600;
}
QMenuBar::item {
    padding: 10px 18px;
}
QMenuBar::item:selected {
    background-color: #3F51B5;
    color: white;
}
QMenu {
    background-color: rgba(200, 200, 200, 150);
    color: #222;
    border: 1px solid #BBB;
    border-radius: 6px;
}
QMenu::item {
    padding: 8px 24px;
}
QMenu::item:selected {
    background-color: #3F51B5;
    color: white;
}
"""
