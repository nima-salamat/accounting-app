# ui/product_panel.py
from ui.base_panel import TableManagement
from db.models import Category

class CategoryManagement(TableManagement):
    def __init__(self, parent=None):
        super().__init__(
            parent,
            display_fields=["id","name", "created_at"],
            create_fields=["name"],
            searchable_fields=["name"],
            field_labels={"name": "نام", "created_at":"زمان ایجاد"},
            initial_sort=[('زمان ایجاد', False), ('نام', True)]

        )
        self.setModel(Category)
