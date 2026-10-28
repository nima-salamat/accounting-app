# ui/product_panel.py
from ui.base_panel import TableManagement
from db.models import Product

class ProductManagement(TableManagement):
    def __init__(self, parent=None):

        super().__init__(
            parent,
            display_fields=["name", "buy_price", "sell_price", "category", "custom_product","image_path","created_at"],
            create_fields=["name", "buy_price", "sell_price", "category", "image_path"],
            searchable_fields=["name", "id", "category", "custom_product"],
            field_labels={"name": "نام", "sell_price": "قیمت فروش", "category": "دسته‌بندی", "created_at":"زمان ایجاد", "image_path":"آدرس عکس", "buy_price":"قیمت خرید", "custom_product":"محصول سفارشی"},
            image_fields=["image_path"],
        )
        self.setModel(Product)
