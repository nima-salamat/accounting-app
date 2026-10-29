"""Shared design tokens, application palette, and QDarkStyle-backed Qt stylesheet."""
from copy import deepcopy
import logging
import re

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QAbstractSpinBox

try:
    import qdarkstyle
    from qdarkstyle.dark.palette import DarkPalette
    from qdarkstyle.light.palette import LightPalette
except ImportError:  # Keep the custom design system available in recovery environments.
    qdarkstyle = None
    DarkPalette = LightPalette = None

_LOGGER = logging.getLogger(__name__)
_CURRENT_MODE = "light"

LIGHT = {
    "window": "#F5F7FB", "surface": "#FFFFFF", "surface_alt": "#F7F9FC",
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
_SPINBOX_WHEEL_GUARD = None


class _NoSpinboxWheelChanges(QObject):
    """Prevent accidental quantity/price changes when scrolling a form or page."""

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            widget = watched
            while widget is not None:
                if isinstance(widget, QAbstractSpinBox):
                    event.accept()
                    return True
                widget = widget.parentWidget() if hasattr(widget, "parentWidget") else None
        return False


def install_spinbox_wheel_guard(app=None):
    """Install one application-wide guard for every QSpinBox/QDoubleSpinBox."""
    global _SPINBOX_WHEEL_GUARD
    app = app or QApplication.instance()
    if app is None:
        return None
    if _SPINBOX_WHEEL_GUARD is None:
        _SPINBOX_WHEEL_GUARD = _NoSpinboxWheelChanges(app)
        app.installEventFilter(_SPINBOX_WHEEL_GUARD)
    return _SPINBOX_WHEEL_GUARD


def normalize_design_config(values=None):
    """Validate server-provided design settings before putting them in Qt stylesheets."""
    source = values if isinstance(values, dict) else {}
    result = dict(DEFAULT_DESIGN)
    family = str(source.get("font_family") or result["font_family"]).strip()
    if not re.fullmatch(r"[\w .()\-]{1,64}", family, flags=re.UNICODE):
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




def current_theme_mode():
    """Return the active application theme, including for dialogs created later."""
    app = QApplication.instance()
    if app is not None:
        configured = app.property("accountingAppThemeMode")
        if configured in ("light", "dark"):
            return configured
    return _CURRENT_MODE


def _apply_application_palette(mode, colors):
    """Make empty viewports and native controls inherit the same app colors."""
    app = QApplication.instance()
    if app is None:
        return
    palette = QPalette(app.palette())
    roles = {
        QPalette.ColorRole.Window: "window",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "surface",
        QPalette.ColorRole.AlternateBase: "surface_alt",
        QPalette.ColorRole.ToolTipBase: "sidebar",
        QPalette.ColorRole.ToolTipText: "sidebar_text",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.Button: "surface",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.BrightText: "danger",
        QPalette.ColorRole.Highlight: "primary",
        QPalette.ColorRole.HighlightedText: "selection_text",
        QPalette.ColorRole.Link: "primary",
        QPalette.ColorRole.PlaceholderText: "muted",
    }
    for role, token in roles.items():
        palette.setColor(role, QColor(colors[token]))
    app.setPalette(palette)
    app.setProperty("accountingAppThemeMode", mode)


def _base_stylesheet(mode):
    """Load QDarkStyle's native-control styles with its matching light/dark palette."""
    if qdarkstyle is None:
        return ""
    palette = DarkPalette if mode == "dark" else LightPalette
    try:
        return qdarkstyle.load_stylesheet(qt_api="pyside6", palette=palette)
    except Exception:
        # Resource failures should not prevent the accounting client from opening.
        _LOGGER.exception("QDarkStyle failed to load; using the application stylesheet fallback.")
        return ""


def stylesheet(mode="light", design=None):
    """Compose QDarkStyle controls with the shared application design tokens."""
    global _CURRENT_MODE
    install_spinbox_wheel_guard()
    mode = "dark" if mode == "dark" else "light"
    _CURRENT_MODE = mode
    colors = dict(DARK if mode == "dark" else LIGHT)
    d = normalize_design_config(_CURRENT_DESIGN if design is None else design)
    density_factor = {"compact": 0.82, "comfortable": 1.0, "spacious": 1.18}[d["density"]]
    colors.update({
        "control_content_height": max(18, round(d["control_height"] - 2 * d["control_padding"] - 2)),
        "font_family": d["font_family"],
        "font_size": d["font_size"],
        "heading_size": round(d["font_size"] * 1.72 * d["heading_scale"]),
        "metric_size": round(d["font_size"] * 2.05 * d["heading_scale"]),
        "corner_radius": d["corner_radius"],
        "control_height": round(d["control_height"] * density_factor),
        "control_padding": round(d["control_padding"] * density_factor),
        "horizontal_padding": d["horizontal_padding"],
        "section_spacing": d["section_spacing"],
        "auth_title_size": round(d["font_size"] * 1.9 * d["heading_scale"]),
        "auth_hero_title_size": round(d["font_size"] * 2.1 * d["heading_scale"]),
        "auth_button_size": round(d["font_size"] * 1.05),
    })
    app_stylesheet = r"""
    * {{ font-family: "{font_family}", "Vazirmatn", "Segoe UI", "Noto Sans Arabic", sans-serif; }}
    QWidget {{ color: {text}; font-size: {font_size}px; background-color: transparent; }}
    QMainWindow, QDialog {{ background: {window}; }}
    QWidget#AppRoot, QWidget#AuthRoot, QWidget#WizardRoot {{ background: {window}; }}
    QFrame#Card, QGroupBox#Card {{ background: {surface}; border: 1px solid {border}; border-radius: {corner_radius}px; }}
    QFrame#SidebarBrandmark {{ background: {primary}; color: #FFFFFF; border-radius: 13px; font-size: 23px; font-weight: 900; }}
    QFrame#AuthCard {{ background: {surface}; border: 1px solid {border}; border-radius: 22px; }}
    QFrame#AuthHero {{ background: {sidebar}; border: 1px solid rgba(255,255,255,0.07); border-radius: 22px; }}
    QFrame#AuthFeature {{ background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; }}
    QFrame#AuthSection {{ background: {surface_alt}; border: 1px solid {border}; border-radius: 14px; }}
    QWidget#AuthForm {{ background: transparent; }}
    QLabel#StatusDot {{ color: {accent}; font-size: 12px; }}
    QLabel#StatusDot[state="error"] {{ color: {danger}; }}
    QLabel#AuthPendingIcon {{ color: {primary}; font-size: 34px; }}
    QLabel#AuthPendingTitle {{ color: {text}; font-size: 18px; font-weight: 800; }}
    QLabel#AuthConnectionStatus[connected="true"] {{ color: {accent}; font-weight: 700; }}
    QFrame#Workbar {{ background: {surface}; border: 1px solid {border}; border-radius: {corner_radius}px; }}
    QFrame#WorkbarPrimaryRow {{ background: transparent; border: none; }}
    QFrame#WorkbarSubmenuRow {{ background: {surface_alt}; border: 1px solid {border}; border-radius: {corner_radius}px; }}
    QFrame#SalesProductCard, QFrame#SalesCartItem {{ background: {surface}; border: 1px solid {border}; border-radius: {corner_radius}px; }}
    QFrame#SalesProductCard:hover {{ border-color: {primary}; }}
    QLabel#SalesProductImage {{ background: {surface_alt}; color: {muted}; border: 1px dashed {border}; border-radius: 8px; padding: 5px; }}
    QLabel#SalesProductTitle {{ color: {text}; font-size: {font_size}px; font-weight: 750; }}
    QLabel#SalesProductPrice {{ color: {primary}; font-size: {font_size + 3}px; font-weight: 850; }}
    QLabel#SalesProductStock {{ background: {highlight}; color: {accent}; border-radius: 7px; padding: 4px 7px; font-size: 11px; }}
    QLabel#SalesProductStock[outOfStock="true"] {{ background: {surface_alt}; color: {danger}; }}
    QLabel#SalesCartItemTitle {{ color: {text}; font-size: {font_size}px; font-weight: 750; }}
    QLabel#SalesCartLineTotal {{ color: {primary}; font-weight: 800; }}
    QSplitter#SalesWorkspaceSplitter::handle {{ background: {border}; width: 6px; margin: 3px 0; border-radius: 3px; }}
    QWidget#HomeBlank {{ background: {window}; }}
    QFrame#Sidebar {{ background: {sidebar}; border: none; }}
    QLabel#Brand {{ font-size: 20px; font-weight: 800; color: {text}; }}
    QLabel#BrandSub {{ color: {muted}; font-size: 11px; }}
    QLabel#PageTitle {{ font-size: {heading_size}px; font-weight: 750; }}
    QLabel#PageSubtitle {{ font-size: {font_size}px; color: {muted}; }}
    QLabel#AuthTitle {{ font-size: {auth_title_size}px; font-weight: 850; color: {text}; }}
    QLabel#AuthEyebrow {{ color: {primary}; font-size: {font_size}px; font-weight: 800; }}
    QLabel#AuthHeroTitle {{ font-size: {auth_hero_title_size}px; font-weight: 900; color: #FFFFFF; }}
    QLabel#AuthHeroSubtitle {{ font-size: {font_size}px; color: #B6C5DC; }}
    QLabel#AuthFeatureTitle {{ font-weight: 800; color: #FFFFFF; }}
    QLabel#AuthFeatureSubtitle {{ color: #9FB0CA; }}
    QLabel#AuthHeroFooter {{ font-size: 10px; color: #7F92B0; }}
    QLabel#AuthSectionTitle {{ font-weight: 800; }}
    QLabel#AuthConnectionStatus {{ color: {muted}; font-size: {font_size}px; }}
    QLabel#AuthMessage {{ color: {danger}; }}
    QLabel#AuthBrandmark {{ background: {primary}; color: white; border-radius: 17px; font-size: 30px; font-weight: 900; }}
    QPushButton#AuthLoginButton {{ background: {primary}; color: white; border: 1px solid {primary}; border-radius: {corner_radius}px; padding: 10px 16px; font-size: {auth_button_size}px; font-weight: 850; }}
    QPushButton#AuthLoginButton:hover {{ background: {primary_hover}; }}
    QPushButton#AuthConnectButton {{ min-width: 78px; background: {surface}; }}
    QLineEdit#AuthInput {{ min-height: 26px; padding: 6px 12px; }}
    QCheckBox#AuthRemember {{ font-weight: 650; padding: 3px 0; }}
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
    QPushButton#CompactActionButton {{ min-height: 24px; padding: 3px 8px; border-radius: {corner_radius}px; }}
    QPushButton#PrimaryButton {{ background: {primary}; color: #FFFFFF; border: 1px solid {primary}; }}
    QPushButton#PrimaryButton:hover {{ background: {primary_hover}; }}
    QPushButton#DangerButton {{ color: {danger}; border-color: {danger}; }}
    QPushButton#GhostButton {{ background: transparent; border-color: transparent; }}
    QPushButton#NavigationButton {{ text-align: right; background: transparent; color: {sidebar_text}; border: none; padding: 12px 14px; border-radius: {corner_radius}px; font-size: {font_size}px; font-weight: 550; }}
    QPushButton#NavigationButton:hover {{ background: rgba(255,255,255,0.08); }}
    QPushButton#NavigationButton[active="true"] {{ background: {primary}; color: #FFFFFF; font-weight: 800; }}
    QPushButton#WorkbarGroupButton {{ background: transparent; border: 1px solid transparent; padding: 7px 15px; min-height: 34px; font-weight: 750; }}
    QPushButton#WorkbarGroupButton:hover {{ background: {highlight}; border-color: {border}; }}
    QPushButton#WorkbarGroupButton[active="true"] {{ background: {primary}; color: #FFFFFF; border-color: {primary}; }}
    QPushButton#WorkbarItemButton {{ background: transparent; border: 1px solid transparent; padding: 5px 12px; min-height: 30px; font-weight: 650; }}
    QPushButton#WorkbarItemButton:hover {{ background: {highlight}; border-color: {border}; }}
    QPushButton#WorkbarItemButton[active="true"] {{ background: {highlight}; color: {primary}; border-color: {border}; font-weight: 800; }}
    QToolButton {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: {corner_radius}px; padding: 7px 13px; font-weight: 700; }}
    QToolButton:hover {{ background: {highlight}; border-color: {primary}; }}
    QMenu {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: {corner_radius}px; padding: 5px; }}
    QMenu::item {{ padding: 9px 24px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {highlight}; color: {primary}; }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTextEdit, QTextBrowser {{
        background: {surface}; color: {text}; border: 1px solid {border}; border-radius: {corner_radius}px;
        padding: {control_padding}px {horizontal_padding}px; min-height: {control_content_height}px;
        selection-background-color: {primary};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{ border: 1px solid {primary}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QTableWidget, QTableView {{ background: {surface}; alternate-background-color: {surface_alt}; border: 1px solid {border}; border-radius: {corner_radius}px; gridline-color: transparent; selection-background-color: {selection}; selection-color: {selection_text}; outline: 0; }}
    QTableWidget#ResourceTable::item:selected, QTableWidget#ResourceTable::item:selected:!active {{ background: {selection}; color: {selection_text}; }}
    QTableWidget::item {{ padding: 9px 8px; border-bottom: 1px solid {border}; }}
    QTableWidget::item:selected, QTableWidget::item:selected:!active, QTableView::item:selected, QListWidget::item:selected {{ background: {selection}; color: {selection_text}; }}
    QHeaderView::section {{ background: {surface_alt}; color: {muted}; border: none; border-bottom: 1px solid {border}; padding: 12px 10px; font-weight: 800; }}
    QTabWidget::pane {{ border: 1px solid {border}; border-radius: {corner_radius}px; top: -1px; }}
    QTabBar::tab {{ padding: 10px 14px; background: {surface_alt}; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
    QTabBar::tab:selected {{ color: {primary}; background: {surface}; font-weight: 800; }}
    QProgressBar {{ border: none; border-radius: 4px; background: {border}; height: 7px; text-align: center; }}
    QProgressBar::chunk {{ background: {primary}; border-radius: 4px; }}
    QScrollArea, QAbstractScrollArea, QStackedWidget {{ border: none; background: transparent; }}
    QScrollArea::viewport, QAbstractScrollArea::viewport {{ background: transparent; border: none; }}
    QSplitter::handle {{ background: {border}; width: 5px; }}
    QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; padding: 3px 2px; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; }}
    QCheckBox:hover, QRadioButton:hover {{ color: {primary}; }}
    QCheckBox:checked, QRadioButton:checked {{ color: {primary}; font-weight: 650; }}
    QGroupBox {{ background: {surface}; color: {text}; border: 1px solid {border}; border-radius: {corner_radius}px; margin-top: 12px; padding: 12px 10px 10px 10px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; color: {text}; background: {surface}; }}
    QListWidget, QListView, QTreeWidget, QTreeView {{ background: {surface}; color: {text}; alternate-background-color: {surface_alt}; border: 1px solid {border}; border-radius: {corner_radius}px; outline: 0; padding: 4px; }}
    QListWidget::item, QListView::item, QTreeWidget::item, QTreeView::item {{ background: transparent; padding: 7px 8px; border-radius: 5px; }}
    QListWidget::item:hover, QListView::item:hover, QTreeWidget::item:hover, QTreeView::item:hover {{ background: {highlight}; color: {text}; }}
    QListWidget::item:selected, QListView::item:selected, QTreeWidget::item:selected, QTreeView::item:selected {{ background: {selection}; color: {selection_text}; }}
    QAbstractItemView {{ background: {surface}; alternate-background-color: {surface_alt}; color: {text}; selection-background-color: {selection}; selection-color: {selection_text}; outline: 0; }}
    QComboBox QAbstractItemView {{ background: {surface}; color: {text}; border: 1px solid {border}; selection-background-color: {selection}; selection-color: {selection_text}; padding: 4px; }}
    QScrollBar:vertical {{ background: {surface_alt}; width: 12px; margin: 2px; border: none; }}
    QScrollBar::handle:vertical {{ background: {border}; min-height: 24px; border-radius: 5px; }}
    QScrollBar::handle:vertical:hover {{ background: {muted}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; border: none; height: 0px; }}
    QScrollBar:horizontal {{ background: {surface_alt}; height: 12px; margin: 2px; border: none; }}
    QScrollBar::handle:horizontal {{ background: {border}; min-width: 24px; border-radius: 5px; }}
    QScrollBar::handle:horizontal:hover {{ background: {muted}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal, QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; border: none; width: 0px; }}
    QToolTip {{ background: {sidebar}; color: {sidebar_text}; border: none; padding: 7px; }}
    QMessageBox {{ background: {surface}; }}
    """.format(**colors)
    app = QApplication.instance()
    if app is not None:
        _apply_application_palette(mode, colors)
    return _base_stylesheet(mode) + "\n" + app_stylesheet
