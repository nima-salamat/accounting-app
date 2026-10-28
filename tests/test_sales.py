import tempfile
import unittest
from pathlib import Path

from accounting_app.database.connection import DBManager, db, initialize_db
from accounting_app.database.models import Category, Product, Receipt, ReceiptProduct, User
from accounting_app.database.schema import create_tables
from accounting_app.services.sales import record_sale


class SalesServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        initialize_db(Path(self.temp_dir.name) / "sales.db")
        with DBManager() as database:
            create_tables(database)
            ReceiptProduct.delete().execute()
            Receipt.delete().execute()
            Product.delete().execute()
            Category.delete().execute()
            User.delete().execute()
            self.user = User(username="cashier", password="", is_admin=False)
            self.user.set_password("cashier password")
            self.user.save(force_insert=True)
            self.category = Category.create(name="General")
            self.product = Product.create(
                name="Test item", buy_price=5.0, sell_price=12.5, category=self.category
            )

    def tearDown(self):
        if not db.is_closed():
            db.close()
        self.temp_dir.cleanup()

    def test_sale_and_line_items_are_persisted_together(self):
        receipt = record_sale({self.product.id: (self.product, 2)}, self.user, True)
        self.assertEqual(receipt.total_price, 25.0)
        with DBManager():
            lines = list(ReceiptProduct.select().where(ReceiptProduct.receipt == receipt.id))
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0].quantity, 2)
            self.assertTrue(Receipt.get_by_id(receipt.id).payed)

    def test_invalid_quantity_does_not_create_a_receipt(self):
        with self.assertRaises(ValueError):
            record_sale({self.product.id: (self.product, 0)}, self.user, True)
        with DBManager():
            self.assertEqual(Receipt.select().count(), 0)

    def test_edit_updates_existing_receipt_and_replaces_lines(self):
        original = record_sale({self.product.id: (self.product, 2)}, self.user, False)
        edited = record_sale(
            {self.product.id: (self.product, 3)},
            self.user,
            True,
            edit_mode=True,
            receipt_to_edit=original,
        )
        self.assertEqual(edited.id, original.id)
        self.assertEqual(edited.total_price, 37.5)
        with DBManager():
            self.assertEqual(Receipt.select().count(), 1)
            lines = list(ReceiptProduct.select().where(ReceiptProduct.receipt == original.id))
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0].quantity, 3)
            self.assertEqual(lines[0].sell_price, 12.5)

    def test_empty_cart_is_rejected(self):
        with self.assertRaises(ValueError):
            record_sale({}, self.user, True)


if __name__ == "__main__":
    unittest.main()
