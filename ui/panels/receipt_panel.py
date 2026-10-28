# ui/product_panel.py
from ui.base_panel import TableManagement
from db.models import Receipt

class ReceiptManagement(TableManagement):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            display_fields=["id","payed", "total_price", "user", "created_at", "day_receipt_id"],
            create_fields=["total_price", "user", "payed"],
            searchable_fields=["id", "user", "total_price", "payed"],
            field_labels={"payed":"وضعیت پرداخت", "total_price":"مبلغ کل", "created_at":"زمان ایجاد", "user":"فروشنده", "day_receipt_id":"آیدی در روز"},
        )
        self.setModel(Receipt)
