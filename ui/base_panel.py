"""Backward-compatible import facade for the reorganized UI packages."""
from importlib import import_module
from pathlib import Path

_MODULES = {
    "auth_page": "ui.pages.auth_page",
    "dashboard": "ui.pages.dashboard",
    "main_window": "ui.pages.main_window",
    "base_panel": "ui.panels.base_panel",
    "category_panel": "ui.panels.category_panel",
    "checks": "ui.panels.checks",
    "home_panel": "ui.panels.home_panel",
    "product_panel": "ui.panels.product_panel",
    "receipt_panel": "ui.panels.receipt_panel",
    "receipt_product_panel": "ui.panels.receipt_product_panel",
    "report_panel": "ui.panels.report_panel",
    "sell_panel": "ui.panels.sell_panel",
    "user_panel": "ui.panels.user_panel",
    "warehouse_panel": "ui.panels.warehouse_panel",
    "dynamic_comparison": "ui.widgets.dynamic_comparison",
    "float_bar": "ui.widgets.float_bar",
    "menu_bar": "ui.widgets.menu_bar",
    "screen_saver": "ui.widgets.screen_saver",
    "thread": "ui.widgets.thread",
    "title_bar": "ui.widgets.title_bar",
    "utils": "ui.widgets.utils",
}

_target = import_module(_MODULES[Path(__file__).stem])
__all__ = getattr(_target, "__all__", [
    name for name in vars(_target) if not name.startswith("_")
])
globals().update({name: getattr(_target, name) for name in __all__})
