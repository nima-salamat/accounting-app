"""Compatibility exports for card widgets used by the point-of-sale UI."""
from ui.panels.sell_card_style import COLORS, get_color_from_name
from ui.panels.product_card import ProductCard
from ui.panels.cart_cards import PanelCartItemCard, CartItemCard
from ui.panels.category_card import CategoryCard

__all__ = [
    "COLORS", "get_color_from_name", "ProductCard", "PanelCartItemCard",
    "CartItemCard", "CategoryCard",
]
