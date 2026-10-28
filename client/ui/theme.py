"""Shared design tokens and stylesheet for all Qt client windows."""
from copy import deepcopy
import re

LIGHT = {
    "window": "#F3F6FB", "surface": "#FFFFFF", "surface_alt": "#F7F9FC",
    "text": "#172337", "muted": "#718096", "border": "#DEE6F0",
    "primary": "#315FAD", "primary_hover": "#244B8B", "accent": "#168779",
    "danger": "#C74455", "sidebar": "#15263D", "sidebar_text": "#E8EFF8",
    "sidebar_muted": "#9BAEC4", "highlight": "#E9F0FB", "selection": "#315C91",
    "selection_text": "#FFFFFF", "shadow": "rgba(24, 43, 70, 0.08)",
}
DARK = {
    "window": "#0C1420", "surface": "#141F2D", "surface_alt": "#1A2939",
    "text": "#E8EEF7", "muted": "#A4B3C6", "border": "#2B3B50",
    "primary": "#719BE8", "primary_hover": "#8CB0F3", "accent": "#59C7AF",
    "danger": "#FF7E89", "sidebar": "#08111D", "sidebar_text": "#E3ECF7",
    "sidebar_muted": "#8A9CB3", "highlight": "#22364D", "selection": "#365F95",
    "selection_text": "#FFFFFF", "shadow": "rgba(0, 0, 0, 0.24)",
}

DEFAULT_DESIGN = {
    "font_family": "Vazirmatn",
    "font_size": 13,
    "heading_scale": 1.0,
    "density": "comfortable",
    "corner_radius": 10,
    "control_height": 36,
    "control_padding": 8,
    "horizontal_padding": 12,
    "section_spacing": 12,
}
_CURRENT_DESIGN = dict(DEFAULT_DESIGN)


def normalize_design_config(values=None):
    """Validate server-provided design settings before putting them in Qt stylesheets."""
    source = values if isinstance(values, dict) else {}
    result = dict(DEFAULT_DESIGN)
    family = str(source.get("font_family") or result["font_family"]).strip()
    if not re.fullmatch(r"[\\w .()\\-]{1,64}", family, flags=re.UNICODE):
        family = result["font_family"]
    result["font_family"] = family
    try:
        result["font_size"] = max(10, min(18, int(source.get("font_size", result["font_size"]))))
    except (TypeError, ValueError):
        pass
    try:
        result["heading_scale"] = max(0.9, min(1.5, float(source.get("heading_scale", result["heading_scale"]))))
    except (TypeError, ValueError):
        pass
    density = str(source.get("density", result["density"]))
    if density in ("compact", "comfortable", "spacious"):
        result["density"] = density
    for key, minimum, maximum in (
        ("corner_radius", 4, 20), ("control_height", 28, 52),
        ("control_padding", 4, 16), ("horizontal_padding", 4, 24),
        ("section_spacing", 4, 24),
    ):
        try:
            result[key] = max(minimum, min(maximum, int(source.get(key, result[key]))))
        except (TypeError, ValueError):
            pass
    return result


def set_design_config(values=None):
    """Update the process-wide shared design tokens from the server database."""
    global _CURRENT_DESIGN
    _CURRENT_DESIGN = normalize_design_config(values)
    return deepcopy(_CURRENT_DESIGN)


def get_design_config():
    return deepcopy(_CURRENT_DESIGN)


def stylesheet(mode="light", design=None):
    """Build a consistent light/dark stylesheet using normalized central design tokens."""
    colors = dict(DARK if mode == "dark" else LIGHT)
    d = normalize_design_config(_CURRENT_DESIGN if design is None else design)
    density_factor = {"compact": 0.82, "comfortable": 1.0, "spacious": 1.18}[d["density"]]
    colors.update({
        "font_family": d["font_family"],
        "font_size": d["font_size"],
        "heading_size": round(d["font_size"] * 1.72 * d["heading_scale"]),
        "metric_size": round(d["font_size"] * 2.05 * d["heading_scale"]),
        "corner_radius": d["corner_radius"],
        "control_height": round(d["control_height"] * density_factor),
        "control_padding": round(d["control_padding"] * density_factor),
        "horizontal_padding": d["horizontal_padding"],
        "section_spacing": d["section_spacing"],
    })
    return r"""
    * {{ font-family: "{font_family}", "Vazirmatn", "Segoe UI", "Noto Sans Arabic", sans-serif; }}
    QWidget {{ color: {text}; font-size: {font_size}px; }}
    QMainWindow, QDialog {{ background: {window}; }}
    QWidget#AppRoot, QWidget#AuthRoot, QWidget#WizardRoot {{ background: {window}; }}
    QFrame#Card, QGroupBox#Card {{ background: {surface}; border: 1px solid {border}; border-radius: {corner_radius}px; }}
    QFrame#Sidebar {{ background: {sidebar}; border: none; }}
    QLabel#Brand {{ font-size: 20px; font-weight: 800; color: {text}; }}
    QLabel#BrandSub {{ color: {muted}; font-size: 11px; }}
    QLabel#PageTitle {{ font-size: {heading_size}px; font-weight: 750; }}
    QLabel#PageSubtitle {{ font-size: {font_size}px; color: {muted}; }}
    QLabel#MetricValue {{ font-size: {metric_size}px; font-weight: 800; }}
    QLabel#MetricLabel {{ font-size: {font_size}px; color: {muted}; }}
    QLabel#Muted {{ color: {muted}; }}
    QLabel#SidebarBrand {{ color: #FFFFFF; font-size: 21px; font-weight: 800; }}
    QLabel#SidebarSub {{ color: {sidebar_muted}; font-size: 11px; }}
    QLabel#SidebarSection {{ color: {sidebar_muted}; font-size: 10px; font-weight: 800; padding: 12px 11px 4px; }}
    QLabel#StatusPill {{ background: {highlight}; color: {primary}; border-radius: {corner_radius}px; padding: 6px 10px; font-weight: 700; }}
    QPushButton {{
        background: {surface}; border: 1px solid {border}; border-radius: {corner_radius}px;
        padding: {control_padding}px {horizontal_padding}px; font-weight: 650; min-height: {control_height}px;
    }}
    QPushButton:hover {{ background: {highlight}; border-color: {primary}; }}
    QPushButton:pressed {{ padding-top: {control_padding}px; padding-bottom: {control_padding}px; }}
    QPushButton:focus {{ border: 2px solid {primary}; }}
    QPushButton:disabled {{ color: {muted}; background: {surface_alt}; }}
    QPushButton#PrimaryButton {{ background: {primary}; color: #FFFFFF; border: 1px solid {primary}; }}
    QPushButton#PrimaryButton:hover {{ background: {primary_hover}; }}
    QPushButton#DangerButton {{ color: {danger}; border-color: {danger}; }}
    QPushButton#GhostButton {{ background: transparent; border-color: transparent; }}
    QPushButton#NavigationButton {{ text-align: right; background: transparent; color: {sidebar_text}; border: none; padding: 12px 14px; border-radius: {corner_radius}px; font-size: {font_size}px; font-weight: 550; }}
    QPushButton#NavigationButton:hover {{ background: rgba(255,255,255,0.08); }}
    QPushButton#NavigationButton[active="true"] {{ background: {primary}; color: #FFFFFF; font-weight: 800; }}
    QToolButton {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: {corner_radius}px; padding: 7px 13px; font-weight: 700; }}
    QToolButton:hover {{ background: {highlight}; border-color: {primary}; }}
    QMenu {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: {corner_radius}px; padding: 5px; }}
    QMenu::item {{ padding: 9px 24px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {highlight}; color: {primary}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTextEdit, QTextBrowser {{
        background: {surface}; color: {text}; border: 1px solid {border}; border-radius: {corner_radius}px;
        padding: {control_padding}px {horizontal_padding}px; min-height: {control_height}px;
        selection-background-color: {primary};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{ border: 1px solid {primary}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QTableWidget {{ background: {surface}; alternate-background-color: {surface_alt}; border: 1px solid {border}; border-radius: {corner_radius}px; gridline-color: transparent; selection-background-color: {selection}; selection-color: {selection_text}; outline: 0; }}
    QTableWidget::item {{ padding: 9px 8px; border-bottom: 1px solid {border}; }}
    QTableWidget::item:selected, QTableWidget::item:selected:!active, QTableView::item:selected, QListWidget::item:selected {{ background: {selection}; color: {selection_text}; }}
    QHeaderView::section {{ background: {surface_alt}; color: {muted}; border: none; border-bottom: 1px solid {border}; padding: 12px 10px; font-weight: 800; }}
    QTabWidget::pane {{ border: 1px solid {border}; border-radius: {corner_radius}px; top: -1px; }}
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
    """.format(**colors)
