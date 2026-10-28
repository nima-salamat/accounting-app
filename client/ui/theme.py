"""Shared light/dark design system for the PySide6 client."""
LIGHT = {
    "window": "#F2F5F9", "surface": "#FFFFFF", "surface_alt": "#F7F9FC",
    "text": "#172337", "muted": "#718096", "border": "#E0E6EF",
    "primary": "#2D5C91", "primary_hover": "#244B78", "accent": "#188779",
    "danger": "#C74455", "sidebar": "#17283E", "sidebar_text": "#E8EFF8",
    "sidebar_muted": "#9BAEC4", "highlight": "#E8F0FA", "shadow": "rgba(24, 43, 70, 0.08)",
}
DARK = {
    "window": "#0C1420", "surface": "#141F2D", "surface_alt": "#1A2939",
    "text": "#E8EEF7", "muted": "#A4B3C6", "border": "#2B3B50",
    "primary": "#7CA8F1", "primary_hover": "#95BAFA", "accent": "#59C7AF",
    "danger": "#FF7E89", "sidebar": "#08111D", "sidebar_text": "#E3ECF7",
    "sidebar_muted": "#8A9CB3", "highlight": "#22364D", "shadow": "rgba(0, 0, 0, 0.24)",
}


def stylesheet(mode="light"):
    c = DARK if mode == "dark" else LIGHT
    return """
    * {{ font-family: "Vazirmatn", "Segoe UI", "Noto Sans Arabic", sans-serif; }}
    QWidget {{ color: {text}; font-size: 13px; }}
    QMainWindow, QDialog {{ background: {window}; }}
    QWidget#AppRoot, QWidget#AuthRoot, QWidget#WizardRoot {{ background: {window}; }}
    QFrame#Card, QGroupBox#Card {{
        background: {surface}; border: 1px solid {border}; border-radius: 13px;
    }}
    QFrame#Sidebar {{ background: {sidebar}; border: none; }}
    QLabel#Brand {{ font-size: 20px; font-weight: 800; color: {text}; }}
    QLabel#BrandSub {{ color: {muted}; font-size: 11px; }}
    QLabel#PageTitle {{ font-size: 23px; font-weight: 750; }}
    QLabel#PageSubtitle {{ font-size: 12px; color: {muted}; }}
    QLabel#MetricValue {{ font-size: 27px; font-weight: 800; }}
    QLabel#MetricLabel {{ font-size: 12px; color: {muted}; }}
    QLabel#Muted {{ color: {muted}; }}
    QLabel#SidebarBrand {{ color: #FFFFFF; font-size: 21px; font-weight: 800; }}
    QLabel#SidebarSub {{ color: {sidebar_muted}; font-size: 11px; }}
    QLabel#SidebarSection {{ color: {sidebar_muted}; font-size: 10px; font-weight: 800; padding: 12px 11px 4px; }}
    QLabel#StatusPill {{ background: {highlight}; color: {primary}; border-radius: 9px; padding: 6px 10px; font-weight: 700; }}
    QPushButton {{
        background: {surface}; border: 1px solid {border}; border-radius: 9px;
        padding: 9px 15px; font-weight: 650; min-height: 18px;
    }}
    QPushButton:hover {{ background: {highlight}; border-color: {primary}; }}
    QPushButton:pressed {{ padding-top: 10px; padding-bottom: 8px; }}
    QPushButton:focus-visible {{ border: 2px solid {primary}; }}
    QPushButton:disabled {{ color: {muted}; background: {surface_alt}; }}
    QPushButton#PrimaryButton {{ background: {primary}; color: #FFFFFF; border: 1px solid {primary}; }}
    QPushButton#PrimaryButton:hover {{ background: {primary_hover}; }}
    QPushButton#DangerButton {{ color: {danger}; border-color: {danger}; }}
    QPushButton#GhostButton {{ background: transparent; border-color: transparent; }}
    QPushButton#NavigationButton {{
        text-align: right; background: transparent; color: {sidebar_text};
        border: none; padding: 12px 14px; border-radius: 9px; font-size: 13px; font-weight: 550;
    }}
    QPushButton#NavigationButton:hover {{ background: rgba(255,255,255,0.08); }}
    QPushButton#NavigationButton[active="true"] {{
        background: {primary}; color: #FFFFFF; font-weight: 800;
    }}
    QLineEdit, QComboBox, QSpinBox, QDateEdit, QDateTimeEdit, QTextEdit {{
        background: {surface}; border: 1px solid {border}; border-radius: 8px;
        padding: 9px 10px; selection-background-color: {primary}; min-height: 18px;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{
        border: 1px solid {primary};
    }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QTableWidget {{
        background: {surface}; alternate-background-color: {surface_alt};
        border: 1px solid {border}; border-radius: 11px; gridline-color: transparent;
        selection-background-color: {highlight}; selection-color: {text}; outline: 0;
    }}
    QTableWidget::item {{ padding: 9px 8px; border-bottom: 1px solid {border}; }}
    QHeaderView::section {{
        background: {surface_alt}; color: {muted}; border: none;
        border-bottom: 1px solid {border}; padding: 12px 10px; font-weight: 800;
    }}
    QTabWidget::pane {{ border: 1px solid {border}; border-radius: 10px; top: -1px; }}
    QTabBar::tab {{ padding: 10px 14px; background: {surface_alt}; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
    QTabBar::tab:selected {{ color: {primary}; background: {surface}; font-weight: 800; }}
    QProgressBar {{ border: none; border-radius: 4px; background: {border}; height: 7px; text-align: center; }}
    QProgressBar::chunk {{ background: {primary}; border-radius: 4px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QSplitter::handle {{ background: {border}; width: 5px; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 17px; height: 17px; }}
    QToolTip {{ background: {sidebar}; color: white; border: none; padding: 7px; }}
    QMessageBox {{ background: {surface}; }}
    """.format(**c)
