"""Central semantic icon mapping for the accounting application's Qt controls."""
import re

try:
    import qtawesome as qta
except ImportError:  # Recovery tools remain usable if optional icon assets are missing.
    qta = None

from PySide6.QtCore import QSize
from client.ui.theme import DARK, LIGHT


ICON_BY_KEY = {
    "home": "fa5s.home", "dashboard": "fa5s.chart-pie", "sales": "fa5s.cash-register",
    "products": "fa5s.boxes", "categories": "fa5s.tags", "warehouse": "fa5s.warehouse",
    "inventory": "fa5s.boxes-stacked", "stocktakes": "fa5s.clipboard-check",
    "accounting": "fa5s.book-open", "management": "fa5s.user-cog",
    "templates": "fa5s.file-invoice", "search": "fa5s.search", "refresh": "fa5s.sync-alt",
    "create": "fa5s.plus", "edit": "fa5s.edit", "delete": "fa5s.trash-alt",
    "export": "fa5s.file-csv", "select": "fa5s.check-square", "clear": "fa5s.times-circle",
    "previous": "fa5s.chevron-right", "next": "fa5s.chevron-left", "history": "fa5s.history",
    "print": "fa5s.print", "checkout": "fa5s.cash-register", "cart": "fa5s.cart-plus",
    "clear_cart": "fa5s.cart-arrow-down", "save": "fa5s.save", "preset": "fa5s.clone",
    "duplicate": "fa5s.clone", "zoom_in": "fa5s.search-plus", "zoom_out": "fa5s.search-minus",
    "fit": "fa5s.expand-arrows-alt", "image": "fa5s.image", "palette": "fa5s.palette",
    "connect": "fa5s.plug", "login": "fa5s.sign-in-alt", "logout": "fa5s.sign-out-alt",
    "settings": "fa5s.cog", "theme_light": "fa5s.sun", "theme_dark": "fa5s.moon",
    "cancel": "fa5s.times", "help": "fa5s.question-circle", "return": "fa5s.undo",
    "detail": "fa5s.info-circle", "payment": "fa5s.credit-card", "minus": "fa5s.minus",
    "plus": "fa5s.plus", "eye": "fa5s.eye", "eye_slash": "fa5s.eye-slash",
}

_TEXT_RULES = (
    (("خروجی csv", "csv"), "export"),
    (("فاکتورهای اخیر", "تاریخچه"), "history"),
    (("نمایش و چاپ", "چاپ", "پرینت"), "print"),
    (("افزودن به سبد", "به سبد"), "cart"),
    (("خالی‌کردن سبد", "خالی کردن سبد"), "clear_cart"),
    (("صفحه قبل", "صفحهٔ قبل", "قبلی", "previous"), "previous"),
    (("صفحه بعد", "صفحهٔ بعد", "بعدی", "next"), "next"),
    (("جست‌وجو", "جستجو", "search", "⌕"), "search"),
    (("بازخوانی", "تازه‌سازی", "refresh", "کالاها"), "refresh"),
    (("مخفی‌کردن", "مخفی کردن", "eye-slash"), "eye_slash"),
    (("نمایش رمز", "show password"), "eye"),
    (("بزرگ‌نمایی", "بزرگ نمایی", "zoom in"), "zoom_in"),
    (("کوچک‌نمایی", "کوچک نمایی", "zoom out"), "zoom_out"),
    (("برازش صفحه", "fit page"), "fit"),
    (("تکثیر", "کپی قالب", "duplicate"), "duplicate"),
    (("استفاده از قالب آماده", "قالب آماده"), "preset"),
    (("رنگ", "palette"), "palette"),
    (("عکس", "image"), "image"),
    (("ذخیره", "save"), "save"),
    (("اتصال", "connect"), "connect"),
    (("راه‌اندازی", "ورود", "login"), "login"),
    (("خروج", "logout"), "logout"),
    (("تنظیمات", "settings"), "settings"),
    (("تم تاریک", "dark theme", "☾"), "theme_dark"),
    (("تم روشن", "light theme", "☀"), "theme_light"),
    (("انتخاب همه", "select all"), "select"),
    (("لغو انتخاب", "لغو انتظار", "بستن", "cancel"), "cancel"),
    (("مرجوعی", "استرداد", "return"), "return"),
    (("پرداخت", "ثبت امن فروش", "checkout"), "checkout"),
    (("جزئیات", "اطلاعات", "detail"), "detail"),
    (("افزودن", "ایجاد", "اضافه"), "create"),
    (("ویرایش", "edit"), "edit"),
    (("حذف", "delete"), "delete"),
    (("صندوق", "فروش"), "checkout"),
)

_PREFIX_GLYPHS = re.compile(r"^\s*[↻＋+−↪☾☀⌕⌂▣▦≡⚙⚑◫◇▤▧☷↙↗↩◷◉✦♙♢⌘←→]+\s*")
_SUFFIX_ARROWS = re.compile(r"\s*[←→]+\s*$")


def icon_for_action(action, text=""):
    """Resolve a stable action ID first, then fall back to known UI wording."""
    key = str(action or "").strip().casefold()
    if key in ICON_BY_KEY:
        return ICON_BY_KEY[key]
    if key.startswith("fa5s."):
        return key
    label = (str(text or "") + " " + str(action or "")).casefold().strip()
    exact = {"☾": "theme_dark", "moon": "theme_dark", "☀": "theme_light", "sun": "theme_light",
             "⌕": "search", "+": "plus", "＋": "plus", "−": "minus", "-": "minus"}
    if label in exact:
        return ICON_BY_KEY[exact[label]]
    for phrases, icon_key in _TEXT_RULES:
        if any(phrase in label for phrase in phrases):
            return ICON_BY_KEY[icon_key]
    return None


def _icon_color(button, mode):
    colors = DARK if mode == "dark" else LIGHT
    name = button.objectName()
    if name in {"PrimaryButton", "AuthLoginButton", "KioskAddButton"}:
        return "#FFFFFF"
    if name == "DangerButton":
        return colors["danger"]
    if name == "NavigationButton":
        return colors["sidebar_text"]
    if bool(button.property("active")) and name in {"WorkbarGroupButton", "WorkbarItemButton"}:
        return "#FFFFFF"
    return colors["primary"]


def set_button_icon(button, action, mode="light", *, accessible_name=None):
    """Apply one theme-tinted icon and remove a redundant leading text glyph."""
    if qta is None or button is None:
        return False
    action_text = str(action or "")
    if button.toolTip() == "تغییر تم روشن / تاریک":
        action_text = "theme_dark" if mode != "dark" else "theme_light"
    icon_name = icon_for_action(action_text, button.text())
    if not icon_name:
        return False
    try:
        icon = qta.icon(icon_name, color=_icon_color(button, mode))
        if icon.isNull():
            return False
    except Exception:
        return False

    original_text = button.text()
    button.setIcon(icon)
    button.setIconSize(QSize(16, 16))
    button.setProperty("appIconAction", action)
    cleaned = _PREFIX_GLYPHS.sub("", original_text, count=1)
    cleaned = _SUFFIX_ARROWS.sub("", cleaned).strip()
    if cleaned != original_text:
        button.setText(cleaned)
    if not button.text().strip():
        button.setAccessibleName(accessible_name or button.toolTip() or str(action or "Action"))
    return True


def apply_button_icons(root, mode="light"):
    """Decorate action buttons in a widget subtree, including when the theme changes."""
    if root is None or qta is None:
        return 0
    from PySide6.QtWidgets import QPushButton

    buttons = [root] if isinstance(root, QPushButton) else root.findChildren(QPushButton)
    count = 0
    for button in buttons:
        if button.toolTip() == "تغییر تم روشن / تاریک":
            action = "theme_dark" if mode != "dark" else "theme_light"
        else:
            action = button.property("appIconAction")
        if not action:
            if not button.icon().isNull():
                continue
            object_name = button.objectName()
            action = object_name if object_name in ICON_BY_KEY else button.text()
        count += bool(set_button_icon(button, action, mode))
    return int(count)
