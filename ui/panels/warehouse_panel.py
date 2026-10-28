
from ui.base_panel import TableManagement
from db.models import Warehouse
class WarehouseManagement(TableManagement):
    def __init__(self, parent=None):
        super().__init__(parent,
                         display_fields=["name", "price", "amount", "unit"],
                         create_fields=["name", "price", "amount", "unit"],
                         searchable_fields=["name", "price", "amount", "unit"],
                         field_labels={"name":"نام محصول", "price":"قیمت", "unit":"یکا", "amount":"مقدار"}
                         )
        self.setModel(Warehouse)
    