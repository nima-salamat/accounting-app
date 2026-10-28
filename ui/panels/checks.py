# ui/product_panel.py
from ui.base_panel import TableManagement
from db.models import CheckIn, CheckOut

class CheckInPanel(TableManagement):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            display_fields=["id","name", "price", "check_id", "date", "payed","created_at"],
            create_fields=["name", "price", "check_id","date","payed"],
            searchable_fields=["id", "name", "check_id", "date", "payed"],
            field_labels={"name": "نام طلبکار", "payed":"وضعیت پرداخت", "price":"مبلغ", "created_at":"زمان ایجاد", "user":"کاربر", "date": "تاریخ وصول", "check_id":"شماره چک"},

        )
        self.setModel(CheckIn)


class CheckOutPanel(TableManagement):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            display_fields=["id","name", "price", "check_id","date", "payed","created_at"],
            create_fields=["name", "price", "check_id", "date","payed"],
            searchable_fields=["id", "name", "check_id","price", "payed"],
            field_labels={"name": "نام بدهکار", "payed":"وضعیت پرداخت", "price":"مبلغ", "created_at":"زمان ایجاد", "user":"کاربر", "date": "تاریخ وصول", "check_id":"شماره چک"},

        )
        self.setModel(CheckOut)
