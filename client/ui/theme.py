"""Shared light/dark design system for the PySide6 client."""
LIGHT = {
    "window": "#F4F7FB", "surface": "#FFFFFF", "surface_alt": "#F8FAFC",
    "text": "#162033", "muted": "#66738A", "border": "#E2E8F0",
    "primary": "#4169E1", "primary_hover": "#3154C6", "accent": "#0F9D83",
    "danger": "#D64045", "sidebar": "#111C33", "sidebar_text": "#D5DEEF",
    "sidebar_muted": "#91A0BB", "highlight": "#EAF0FF", "shadow": "rgba(19, 37, 71, 0.06)",
}
DARK = {
    "window": "#0B1220", "surface": "#131E30", "surface_alt": "#17243A",
    "text": "#E8EEF8", "muted": "#A4B2C8", "border": "#2B3A52",
    "primary": "#829BFF", "primary_hover": "#9CB0FF", "accent": "#4DC8AB",
    "danger": "#FF7478", "sidebar": "#070D18", "sidebar_text": "#DFE7F6",
    "sidebar_muted": "#7F90AD", "highlight": "#233251", "shadow": "rgba(0, 0, 0, 0.16)",
}


def stylesheet(mode="light"):
    c = DARK if mode == "dark" else LIGHT
    return """
    * {{ font-family: "Segoe UI", "Noto Sans Arabic", "Vazirmatn", sans-serif; }}
    QWidget {{ color: {text}; font-size: 13px; }}
    QMainWindow, QDialog {{ background: {window}; }}
    QWidget#AppRoot, QWidget#AuthRoot, QWidget#WizardRoot {{ background: {window}; }}
    QFrame#Card, QGroupBox#Card {{
        background: {surface}; border: 1px solid {border}; border-radius: 14px;
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
        background: {surface}; border: 1px solid {border}; border-radius: 8px;
        padding: 9px 14px; font-weight: 600;
    }}
    QPushButton:hover {{ background: {highlight}; border-color: {primary}; }}
    QPushButton:disabled {{ color: {muted}; background: {surface_alt}; }}
    QPushButton#PrimaryButton {{ background: {primary}; color: #FFFFFF; border: 1px solid {primary}; }}
    QPushButton#PrimaryButton:hover {{ background: {primary_hover}; }}
    QPushButton#DangerButton {{ color: {danger}; border-color: {danger}; }}
    QPushButton#GhostButton {{ background: transparent; border-color: transparent; }}
    QPushButton#NavigationButton {{
        text-align: right; background: transparent; color: {sidebar_text};
        border: none; padding: 11px 13px; border-radius: 9px; font-size: 13px;
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
        border: 1px solid {border}; border-radius: 10px; gridline-color: {border};
        selection-background-color: {highlight}; selection-color: {text};
    }}
    QTableWidget::item {{ padding: 7px; border-bottom: 1px solid {border}; }}
    QHeaderView::section {{
        background: {surface_alt}; color: {muted}; border: none;
        border-bottom: 1px solid {border}; padding: 10px; font-weight: 800;
    }}
    QTabWidget::pane {{ border: 1px solid {border}; border-radius: 10px; top: -1px; }}
    QTabBar::tab {{ padding: 10px 14px; background: {surface_alt}; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
    QTabBar::tab:selected {{ color: {primary}; background: {surface}; font-weight: 800; }}
    QProgressBar {{ border: none; border-radius: 4px; background: {border}; height: 7px; text-align: center; }}
    QProgressBar::chunk {{ background: {primary}; border-radius: 4px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QToolTip {{ background: {sidebar}; color: white; border: none; padding: 7px; }}
    QMessageBox {{ background: {surface}; }}
    """.format(**c)
