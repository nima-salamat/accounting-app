# ui/product_panel.py
from ui.base_panel import TableManagement
from db.models import ReceiptProduct

class ReceiptProductManagement(TableManagement):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            display_fields=["product", "receipt", "buy_price", "sell_price", "quantity"],
            create_fields=["product", "receipt", "sell_price", "buy_price", "quantity"],
            searchable_fields=["product", "receipt", "id"],
            field_labels={"product": "محصول", "buy_price": "قیمت حرید", "quantity": "تعداد", "receipt":"رسید", "sell_price": "قیمت فروش"},

        )
        self.setModel(ReceiptProduct)
