import tempfile
import unittest
from pathlib import Path

from accounting_app.database.connection import DBManager, db, initialize_db
from accounting_app.database.extension_models import (
    CustomFieldDefinition, CustomFieldValue, CustomModelDefinition, CustomRecord,
)
from accounting_app.database.models import Product, User
from accounting_app.database.schema import create_tables
from accounting_app.services.authentication import AuthManager
from accounting_app.services.installer import complete_initial_setup, is_setup_required
from accounting_app.services.schema_registry import (
    cleanup_builtin_extension_values, cleanup_builtin_extension_values_many,
    get_entity_values, register_field, save_entity_values,
)
from manager.db import create_admin


class InstallerAndSchemaRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        initialize_db(Path(self.temp_dir.name) / "installer.db")
        with DBManager() as database:
            create_tables(database)

    def tearDown(self):
        if not db.is_closed():
            db.close()
        self.temp_dir.cleanup()

    def test_fresh_database_requires_installation(self):
        self.assertTrue(is_setup_required())
        with DBManager():
            self.assertEqual(User.select().count(), 0)

    def test_legacy_admin_helper_does_not_create_default_credentials(self):
        with self.assertRaises(ValueError):
            create_admin()
        with DBManager():
            self.assertEqual(User.select().count(), 0)

    def test_existing_database_with_users_skips_wizard(self):
        with DBManager():
            user = User(username="legacy_admin", password="legacy-hash", is_admin=True)
            user.save(force_insert=True)
        self.assertFalse(is_setup_required())
        with DBManager():
            from accounting_app.database.extension_models import AppSetting
            marker = AppSetting.get(AppSetting.key == "initial_setup_complete")
            self.assertEqual(marker.value, "1")
            self.assertEqual(User.select().count(), 1)

    def test_setup_can_recover_when_marker_exists_but_no_users_remain(self):
        from accounting_app.database.extension_models import AppSetting
        with DBManager():
            AppSetting.create(key="initial_setup_complete", value="1")
        self.assertTrue(is_setup_required())
        complete_initial_setup("recovered_admin", "password123", "password123")
        self.assertFalse(is_setup_required())

    def test_installer_creates_custom_model_and_hashed_admin(self):
        rows = [
            {
                "model_key": "products", "model_label": "",
                "field_key": "serial_number", "field_label": "شماره سریال",
                "field_type": "text", "is_required": True,
            },
            {
                "model_key": "contacts", "model_label": "مخاطبان",
                "field_key": "full_name", "field_label": "نام کامل",
                "field_type": "text", "is_required": True,
            },
            {
                "model_key": "contacts", "model_label": "",
                "field_key": "age", "field_label": "سن",
                "field_type": "integer", "is_required": False,
            },
        ]
        user = complete_initial_setup("alice", "a secure password", "a secure password", rows)

        self.assertEqual(user.username, "alice")
        self.assertTrue(user.is_admin)
        self.assertNotEqual(user.password, "a secure password")
        self.assertFalse(is_setup_required())
        manager = AuthManager()
        self.assertTrue(manager.validate("alice", "a secure password"))
        with DBManager():
            self.assertEqual(User.select().count(), 1)
            self.assertEqual(CustomModelDefinition.get().model_key, "contacts")
            self.assertEqual(CustomFieldDefinition.select().count(), 3)

    def test_multiple_fields_on_one_new_model_can_share_one_model_label(self):
        rows = [
            {
                "model_key": "assets", "model_label": "دارایی‌ها",
                "field_key": "asset_name", "field_label": "نام",
                "field_type": "text", "is_required": True,
            },
            {
                "model_key": "assets", "model_label": "",
                "field_key": "purchase_price", "field_label": "قیمت خرید",
                "field_type": "decimal", "is_required": False,
            },
        ]
        complete_initial_setup("alice", "password123", "password123", rows)
        record_id = save_entity_values(
            "assets", None, {"asset_name": "لپ‌تاپ", "purchase_price": "1250.50"}
        )
        self.assertTrue(record_id)
        values = get_entity_values("assets", record_id)
        self.assertEqual(values["asset_name"], "لپ‌تاپ")
        self.assertEqual(values["purchase_price"], "1250.50")
        with DBManager():
            self.assertEqual(CustomRecord.select().count(), 1)

    def test_extension_values_attach_to_existing_builtin_record(self):
        complete_initial_setup(
            "alice", "password123", "password123",
            [{
                "model_key": "products", "model_label": "",
                "field_key": "sku_code", "field_label": "کد کالا",
                "field_type": "text", "is_required": True,
            }],
        )
        with DBManager():
            product = Product.create(name="قلم", buy_price=1, sell_price=2)
            product_id = str(product.id)
        saved_id = save_entity_values("products", product_id, {"sku_code": "P-001"})
        self.assertEqual(saved_id, product_id)
        self.assertEqual(get_entity_values("products", product_id), {"sku_code": "P-001"})
        with DBManager():
            self.assertEqual(Product.select().count(), 1)
            self.assertEqual(CustomFieldValue.select().count(), 1)

    def test_invalid_schema_rolls_back_admin_and_metadata(self):
        rows = [
            {
                "model_key": "clients", "model_label": "مشتریان",
                "field_key": "name", "field_label": "نام",
                "field_type": "text", "is_required": True,
            },
            {
                "model_key": "clients", "model_label": "",
                "field_key": "name", "field_label": "نام تکراری",
                "field_type": "text", "is_required": False,
            },
        ]
        with self.assertRaises(ValueError):
            complete_initial_setup("alice", "password123", "password123", rows)
        with DBManager():
            self.assertEqual(User.select().count(), 0)
            self.assertEqual(CustomModelDefinition.select().count(), 0)
            self.assertEqual(CustomFieldDefinition.select().count(), 0)
        self.assertTrue(is_setup_required())

    def test_required_and_typed_values_are_validated(self):
        complete_initial_setup(
            "alice", "password123", "password123",
            [{
                "model_key": "people", "model_label": "افراد",
                "field_key": "age", "field_label": "سن",
                "field_type": "integer", "is_required": True,
            }],
        )
        with self.assertRaises(ValueError):
            save_entity_values("people", None, {"age": "not an integer"})
        with self.assertRaises(ValueError):
            save_entity_values("people", None, {})
        with DBManager():
            self.assertEqual(CustomRecord.select().count(), 0)

    def test_later_custom_field_can_be_added_without_altering_core_table(self):
        complete_initial_setup("alice", "password123", "password123")
        register_field(
            "products", "warranty_months", "مدت ضمانت",
            field_type="integer", is_required=False,
        )
        with DBManager():
            product = Product.create(name="ماوس", buy_price=4, sell_price=7)
            product_id = str(product.id)
        save_entity_values("products", product_id, {"warranty_months": "24"})
        self.assertEqual(get_entity_values("products", product_id), {"warranty_months": 24})
        cleanup_builtin_extension_values("products", product_id)
        self.assertEqual(get_entity_values("products", product_id), {})

    def test_batch_cleanup_removes_only_selected_records(self):
        complete_initial_setup(
            "alice", "password123", "password123",
            [{
                "model_key": "products", "model_label": "",
                "field_key": "external_sku", "field_label": "کد خارجی",
                "field_type": "text", "is_required": False,
            }],
        )
        with DBManager():
            products = [
                Product.create(name="کالا {}".format(index), buy_price=1, sell_price=2)
                for index in range(3)
            ]
        ids = [str(product.id) for product in products]
        for product_id, value in zip(ids, ("A", "B", "C")):
            save_entity_values("products", product_id, {"external_sku": value})

        deleted = cleanup_builtin_extension_values_many("products", ids[:2])
        self.assertEqual(deleted, 2)
        self.assertEqual(get_entity_values("products", ids[0]), {})
        self.assertEqual(get_entity_values("products", ids[1]), {})
        self.assertEqual(get_entity_values("products", ids[2]), {"external_sku": "C"})


if __name__ == "__main__":
    unittest.main()
