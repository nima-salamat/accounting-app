from .models import (
    Category,
    Product,
    Receipt,
    ReceiptProduct,
    User,
    Warehouse, 
    CheckIn, 
    CheckOut
)
def create(db):
    db.create_tables([Category, Product, Receipt, ReceiptProduct, User, Warehouse, CheckOut, CheckIn])
