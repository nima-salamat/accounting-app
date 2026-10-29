"""End-to-end tests for the FastAPI boundary using a temporary SQLite database."""
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

os.environ.setdefault("ACCOUNTING_APP_SECRET_KEY", "test-signing-key-with-more-than-32-characters")

from fastapi import HTTPException
from fastapi.testclient import TestClient

from accounting_app.database.connection import DBManager, db, initialize_db
from accounting_app.database.models import Product, Receipt
from manager.db import create_db
from server.app.main import app
from server.app.api.auth import _authorize_setup
from server.app.schemas import SetupRequest
from accounting_app.services.invoice_numbering import format_invoice_number, validate_invoice_number_format


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        initialize_db(Path(self.temp_dir.name) / "api-test.db")
        create_db()
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        if not db.is_closed():
            db.close()
        self.temp_dir.cleanup()

    def setup_admin(self):
        response = self.client.post(
            "/api/v1/setup",
            json={
                "username": "alice",
                "password": "correct horse",
                "password_confirmation": "correct horse",
                "schema_rows": [],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        token = response.json()["access_token"]
        return {"Authorization": "Bearer " + token}

    def test_health_setup_and_authenticated_identity(self):
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        self.assertTrue(self.client.get("/api/v1/setup/status").json()["setup_required"])
        headers = self.setup_admin()
        self.assertFalse(self.client.get("/api/v1/setup/status").json()["setup_required"])
        identity = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(identity.status_code, 200)
        self.assertEqual(identity.json()["username"], "alice")
        self.assertTrue(identity.json()["is_admin"])
        self.assertEqual(
            self.client.post(
                "/api/v1/setup",
                json={
                    "username": "bobby",
                    "password": "password",
                    "password_confirmation": "password",
                },
            ).status_code,
            409,
        )

    def test_appearance_settings_are_shared_and_admin_only_writable(self):
        initial = self.client.get("/api/v1/appearance-settings")
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertEqual(initial.json()["font_family"], "Vazirmatn")
        self.assertEqual(
            self.client.put("/api/v1/appearance-settings", json={"font_family": "Tahoma"}).status_code,
            401,
        )
        headers = self.setup_admin()
        payload = {
            "font_family": "Noto Sans Arabic", "font_size": 15,
            "heading_scale": 1.2, "density": "spacious", "corner_radius": 12,
            "control_height": 40, "control_padding": 9,
            "horizontal_padding": 14, "section_spacing": 16,
        }
        saved = self.client.put("/api/v1/appearance-settings", headers=headers, json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json(), payload)
        self.assertEqual(self.client.get("/api/v1/appearance-settings").json(), payload)

    def test_products_are_authorized_validated_and_serialized(self):
        headers = self.setup_admin()
        self.assertEqual(self.client.get("/api/v1/products").status_code, 401)
        category = self.client.post(
            "/api/v1/categories", headers=headers, json={"name": "لوازم"}
        )
        self.assertEqual(category.status_code, 201, category.text)
        product = self.client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "name": "قلم",
                "buy_price": "2.5",
                "sell_price": "4.75",
                "category_id": category.json()["id"],
            },
        )
        self.assertEqual(product.status_code, 201, product.text)
        self.assertEqual(product.json()["name"], "قلم")
        self.assertEqual(product.json()["category_id"], category.json()["id"])
        self.assertEqual(
            len(self.client.get("/api/v1/products?q=قلم", headers=headers).json()), 1
        )
        rejected = self.client.post(
            "/api/v1/products",
            headers=headers,
            json={"name": "نامعتبر", "buy_price": -1, "sell_price": 0},
        )
        self.assertEqual(rejected.status_code, 422)

    def test_sale_idempotency_and_summary(self):
        headers = self.setup_admin()
        product = self.client.post(
            "/api/v1/products",
            headers=headers,
            json={"name": "کالا", "buy_price": "3", "sell_price": "6.25"},
        ).json()
        sale = {
            "items": [{"product_id": product["id"], "quantity": 2}],
            "paid": True,
        }
        sale_headers = dict(headers, **{"Idempotency-Key": "test-sale-0001"})
        first = self.client.post("/api/v1/sales", headers=sale_headers, json=sale)
        self.assertEqual(first.status_code, 201, first.text)
        second = self.client.post("/api/v1/sales", headers=sale_headers, json=sale)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(first.json()["total_price"], 12.5)
        self.assertEqual(len(first.json()["items"]), 1)
        self.assertEqual(len(self.client.get("/api/v1/receipts", headers=headers).json()), 1)
        summary = self.client.get("/api/v1/reports/summary", headers=headers)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["receipt_count"], 1)
        self.assertEqual(summary.json()["paid_count"], 1)
        self.assertEqual(summary.json()["item_count"], 2)
        with DBManager():
            self.assertEqual(Receipt.select().count(), 1)

        trend = self.client.get("/api/v1/reports/sales-trend?days=30", headers=headers)
        self.assertEqual(trend.status_code, 200, trend.text)
        performance = self.client.get("/api/v1/reports/product-performance", headers=headers)
        self.assertEqual(performance.status_code, 200, performance.text)
        self.assertEqual(performance.json()[0]["name"], "کالا")

    def test_idempotency_key_cannot_be_reused_for_different_sale(self):
        headers = self.setup_admin()
        product = self.client.post(
            "/api/v1/products", headers=headers,
            json={"name": "کالا", "buy_price": 1, "sell_price": 2},
        ).json()
        key_headers = dict(headers, **{"Idempotency-Key": "test-sale-0002"})
        first = {"items": [{"product_id": product["id"], "quantity": 1}], "paid": False}
        second = {"items": [{"product_id": product["id"], "quantity": 2}], "paid": False}
        self.assertEqual(self.client.post("/api/v1/sales", headers=key_headers, json=first).status_code, 201)
        conflict = self.client.post("/api/v1/sales", headers=key_headers, json=second)
        self.assertEqual(conflict.status_code, 409)
        with DBManager():
            self.assertEqual(Receipt.select().count(), 1)

    def test_non_admin_can_sell_but_cannot_manage_products_or_users(self):
        admin_headers = self.setup_admin()
        created = self.client.post(
            "/api/v1/users", headers=admin_headers,
            json={"username": "cashier", "password": "cashier-password", "is_admin": False, "requires_session_activation": False},
        )
        self.assertEqual(created.status_code, 201, created.text)
        login = self.client.post(
            "/api/v1/auth/login",
            json={"username": "cashier", "password": "cashier-password"},
        )
        cashier_headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        self.assertEqual(self.client.get("/api/v1/products", headers=cashier_headers).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/users", headers=cashier_headers).status_code, 403)
        denied = self.client.post(
            "/api/v1/products", headers=cashier_headers,
            json={"name": "نباید ساخته شود", "buy_price": 1, "sell_price": 2},
        )
        self.assertEqual(denied.status_code, 403)

    def test_new_device_waits_for_admin_activation_and_revocation_is_immediate(self):
        admin_headers = self.setup_admin()
        created = self.client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "username": "new_cashier",
                "password": "new-cashier-password",
                "is_admin": False,
                "is_active": True,
                "requires_session_activation": True,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertTrue(created.json()["requires_session_activation"])

        pending = self.client.post(
            "/api/v1/auth/login",
            json={
                "username": "new_cashier",
                "password": "new-cashier-password",
                "client_name": "Front desk PC",
            },
        )
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertEqual(pending.json()["status"], "pending_activation")
        self.assertIsNone(pending.json().get("access_token"))
        ticket = pending.json()["session_ticket"]
        check = self.client.post("/api/v1/auth/session-status", json={"ticket": ticket})
        self.assertEqual(check.status_code, 200, check.text)
        self.assertEqual(check.json()["status"], "pending_activation")

        pending_sessions = self.client.get(
            "/api/v1/admin/sessions?state=pending", headers=admin_headers
        )
        self.assertEqual(pending_sessions.status_code, 200, pending_sessions.text)
        self.assertEqual(len(pending_sessions.json()), 1)
        session_id = pending_sessions.json()[0]["id"]
        self.assertEqual(pending_sessions.json()[0]["client_name"], "Front desk PC")

        activated = self.client.post(
            "/api/v1/admin/sessions/{}/activate".format(session_id),
            headers=admin_headers,
        )
        self.assertEqual(activated.status_code, 200, activated.text)
        self.assertEqual(activated.json()["status"], "active")
        active_status = self.client.post(
            "/api/v1/auth/session-status", json={"ticket": ticket}
        )
        self.assertEqual(active_status.status_code, 200, active_status.text)
        self.assertEqual(active_status.json()["status"], "active")
        cashier_headers = {"Authorization": "Bearer " + active_status.json()["access_token"]}
        self.assertEqual(self.client.get("/api/v1/auth/me", headers=cashier_headers).status_code, 200)

        revoked = self.client.post(
            "/api/v1/admin/sessions/{}/revoke".format(session_id),
            headers=admin_headers,
            json={"reason": "admin_test_revocation"},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        denied = self.client.get("/api/v1/products", headers=cashier_headers)
        self.assertEqual(denied.status_code, 401)

    def test_user_session_limit_defaults_to_one_and_admin_can_raise_it(self):
        admin_headers = self.setup_admin()
        created = self.client.post(
            "/api/v1/users", headers=admin_headers,
            json={"username": "single_user", "password": "single-user-password",
                  "is_admin": False, "requires_session_activation": False},
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["max_active_sessions"], 1)

        first_login = self.client.post(
            "/api/v1/auth/login",
            json={"username": "single_user", "password": "single-user-password", "client_name": "PC 1"},
        )
        self.assertEqual(first_login.status_code, 200, first_login.text)
        token_one = first_login.json()["access_token"]
        self.assertEqual(self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token_one}).status_code, 200)

        second_login = self.client.post(
            "/api/v1/auth/login",
            json={"username": "single_user", "password": "single-user-password", "client_name": "PC 2"},
        )
        self.assertEqual(second_login.status_code, 200, second_login.text)
        token_two = second_login.json()["access_token"]
        self.assertEqual(self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token_one}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token_two}).status_code, 200)

        updated = self.client.patch(
            "/api/v1/users/{}".format(created.json()["id"]),
            headers=admin_headers, json={"max_active_sessions": 2},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["max_active_sessions"], 2)

        third_login = self.client.post(
            "/api/v1/auth/login",
            json={"username": "single_user", "password": "single-user-password", "client_name": "PC 3"},
        )
        fourth_login = self.client.post(
            "/api/v1/auth/login",
            json={"username": "single_user", "password": "single-user-password", "client_name": "PC 4"},
        )
        self.assertEqual(third_login.status_code, 200, third_login.text)
        self.assertEqual(fourth_login.status_code, 200, fourth_login.text)
        token_three = third_login.json()["access_token"]
        token_four = fourth_login.json()["access_token"]
        self.assertEqual(self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token_three}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token_four}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token_two}).status_code, 401)

    def test_invoice_number_format_helpers_support_examples_and_overflow(self):
        receipt = {
            "created_at": "2026-10-30T16:45:00",
            "day_receipt_id": 1,
            "invoice_sequence": 100001,
        }
        self.assertEqual(format_invoice_number(receipt, "{DATE}-{NUM}", 5), "2026-10-30-00001")
        self.assertEqual(format_invoice_number(receipt, "{YYYY}-{MM}-{D}-NUM-{NUM}", 5), "2026-10-30-NUM-00001")
        self.assertEqual(format_invoice_number(receipt, "{SEQ}", 5), "100001")
        self.assertEqual(
            format_invoice_number(dict(receipt, day_receipt_id=100001), "{DATE}-{NUM}", 5),
            "2026-10-30-100001",
        )
        with self.assertRaises(ValueError):
            validate_invoice_number_format("INV-{DD}")

    def test_invoice_number_format_is_persisted_and_invalid_patterns_are_rejected(self):
        headers = self.setup_admin()
        saved = self.client.put(
            "/api/v1/invoices/template", headers=headers,
            json={"invoice_number_format": "INV-{YYYY}-{MM}-{D}-{NUM}", "invoice_number_padding": 7},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["invoice_number_format"], "INV-{YYYY}-{MM}-{D}-{NUM}")
        self.assertEqual(saved.json()["invoice_number_padding"], 7)
        fetched = self.client.get("/api/v1/invoices/template", headers=headers)
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json()["invoice_number_format"], "INV-{YYYY}-{MM}-{D}-{NUM}")
        self.assertEqual(fetched.json()["invoice_number_padding"], 7)
        invalid = self.client.put(
            "/api/v1/invoices/template", headers=headers, json={"invoice_number_format": "INV-{DD}"}
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)

    def test_new_sales_persist_invoice_numbers_and_format_changes_do_not_renumber_history(self):
        headers = self.setup_admin()
        product = self.client.post(
            "/api/v1/products",
            headers=headers,
            json={"name": "کالا", "buy_price": "3", "sell_price": "6.25"},
        ).json()
        saved = self.client.put(
            "/api/v1/invoices/template", headers=headers,
            json={"invoice_number_format": "{DATE}-{NUM}", "invoice_number_padding": 5},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        first = self.client.post(
            "/api/v1/sales", headers=dict(headers, **{"Idempotency-Key": "number-sale-1"}),
            json={"items": [{"product_id": product["id"], "quantity": 1}], "paid": True},
        )
        self.assertEqual(first.status_code, 201, first.text)
        first_payload = first.json()
        self.assertRegex(first_payload["invoice_number"], r"^\d{4}-\d{2}-\d{2}-00001$")
        with DBManager():
            first_row = Receipt.get_by_id(first_payload["id"])
            self.assertEqual(first_row.invoice_sequence, 1)

        changed = self.client.put(
            "/api/v1/invoices/template", headers=headers,
            json={"invoice_number_format": "INV-{SEQ}", "invoice_number_padding": 5},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        second = self.client.post(
            "/api/v1/sales", headers=dict(headers, **{"Idempotency-Key": "number-sale-2"}),
            json={"items": [{"product_id": product["id"], "quantity": 1}], "paid": True},
        )
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()["invoice_number"], "INV-00002")
        old = self.client.get("/api/v1/receipts/{}".format(first_payload["id"]), headers=headers)
        self.assertEqual(old.status_code, 200, old.text)
        self.assertEqual(old.json()["invoice_number"], first_payload["invoice_number"])

    def test_invoice_template_persists_dragged_element_positions(self):
        headers = self.setup_admin()
        element = {
            "id": "invoice-date", "type": "invoice_date", "label": "تاریخ",
            "x_mm": 13, "y_mm": 11, "w_mm": 61, "h_mm": 9,
            "font_size": 10, "align": "left", "bold": False, "visible": True, "text": "",
        }
        saved = self.client.put(
            "/api/v1/invoices/template", headers=headers,
            json={"company_name": "فروشگاه آزمایشی", "paper_size": "A4",
                  "orientation": "landscape", "show_border": True, "elements": [element]},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["orientation"], "landscape")
        self.assertEqual(saved.json()["elements"][0]["x_mm"], 13)
        fetched = self.client.get("/api/v1/invoices/template", headers=headers)
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json()["elements"], saved.json()["elements"])
        self.assertTrue(fetched.json()["show_border"])

    def test_invoice_templates_are_independent_for_each_print_workflow(self):
        headers = self.setup_admin()
        default_invoice = self.client.get("/api/v1/invoices/template", headers=headers)
        pos_default = self.client.get("/api/v1/invoices/template?kind=pos_receipt", headers=headers)
        kiosk_default = self.client.get("/api/v1/invoices/template?kind=kiosk_receipt", headers=headers)
        self.assertEqual(default_invoice.status_code, 200, default_invoice.text)
        self.assertEqual(pos_default.status_code, 200, pos_default.text)
        self.assertEqual(kiosk_default.status_code, 200, kiosk_default.text)
        original_invoice_name = default_invoice.json()["company_name"]
        self.assertEqual(default_invoice.json()["paper_size"], "A4")
        self.assertEqual(pos_default.json()["paper_size"], "receipt80")
        self.assertEqual(kiosk_default.json()["paper_size"], "receipt80")

        saved_pos = self.client.put(
            "/api/v1/invoices/template?kind=pos_receipt", headers=headers,
            json={"company_name": "رسید صندوق مستقل", "paper_size": "receipt80",
                  "orientation": "portrait", "margin_mm": 4},
        )
        self.assertEqual(saved_pos.status_code, 200, saved_pos.text)
        fetched_pos = self.client.get("/api/v1/invoices/template?kind=pos_receipt", headers=headers)
        fetched_invoice = self.client.get("/api/v1/invoices/template", headers=headers)
        self.assertEqual(fetched_pos.json()["company_name"], "رسید صندوق مستقل")
        self.assertEqual(fetched_invoice.json()["company_name"], original_invoice_name)

    def test_inactive_accounts_cannot_login(self):
        admin_headers = self.setup_admin()
        created = self.client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "username": "disabled_user",
                "password": "disabled-user-password",
                "is_admin": False,
                "is_active": False,
                "requires_session_activation": False,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        login = self.client.post(
            "/api/v1/auth/login",
            json={"username": "disabled_user", "password": "disabled-user-password"},
        )
        self.assertEqual(login.status_code, 401)

    def test_tracked_inventory_adjustments_and_sales_are_atomic(self):
        admin_headers = self.setup_admin()
        created = self.client.post(
            "/api/v1/products",
            headers=admin_headers,
            json={
                "name": "کالای انباردار",
                "buy_price": 10,
                "sell_price": 15,
                "track_stock": True,
                "reorder_level": 2,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        product = created.json()
        self.assertTrue(product["track_stock"])
        self.assertEqual(product["stock_quantity"], 0)

        opening = self.client.post(
            "/api/v1/inventory/adjustments",
            headers=admin_headers,
            json={
                "product_id": product["id"],
                "quantity_change": "3",
                "reason": "opening",
                "notes": "موجودی اولیه",
            },
        )
        self.assertEqual(opening.status_code, 201, opening.text)
        self.assertEqual(opening.json()["stock_after"], 3)

        first_sale = self.client.post(
            "/api/v1/sales",
            headers=dict(admin_headers, **{"Idempotency-Key": "stock-sale-0001"}),
            json={"items": [{"product_id": product["id"], "quantity": 2}], "paid": True},
        )
        self.assertEqual(first_sale.status_code, 201, first_sale.text)
        self.assertEqual(first_sale.json()["items"][0]["product_name"], "کالای انباردار")

        inventory = self.client.get(
            "/api/v1/inventory?q=کالای انباردار",
            headers=admin_headers,
        )
        self.assertEqual(inventory.status_code, 200, inventory.text)
        self.assertEqual(inventory.json()["total"], 1)
        self.assertEqual(inventory.json()["items"][0]["stock_quantity"], 1)

        oversell = self.client.post(
            "/api/v1/sales",
            headers=dict(admin_headers, **{"Idempotency-Key": "stock-sale-0002"}),
            json={"items": [{"product_id": product["id"], "quantity": 2}], "paid": False},
        )
        self.assertEqual(oversell.status_code, 409, oversell.text)
        inventory_after = self.client.get(
            "/api/v1/inventory?q=کالای انباردار",
            headers=admin_headers,
        ).json()
        self.assertEqual(inventory_after["items"][0]["stock_quantity"], 1)
        edited_sale = self.client.put(
            "/api/v1/sales/{}".format(first_sale.json()["id"]),
            headers=admin_headers,
            json={"items": [{"product_id": product["id"], "quantity": 1}], "paid": True},
        )
        self.assertEqual(edited_sale.status_code, 200, edited_sale.text)
        inventory_after_edit = self.client.get(
            "/api/v1/inventory?q=کالای انباردار",
            headers=admin_headers,
        ).json()
        self.assertEqual(inventory_after_edit["items"][0]["stock_quantity"], 2)
        self.assertEqual(edited_sale.json()["items"][0]["quantity"], 1)

        movements = self.client.get(
            "/api/v1/inventory/movements?product_id={}".format(product["id"]),
            headers=admin_headers,
        )
        self.assertEqual(movements.status_code, 200, movements.text)
        self.assertEqual(movements.json()["total"], 4)
        self.assertEqual(
            len(self.client.get("/api/v1/receipts", headers=admin_headers).json()),
            1,
        )
        protected_delete = self.client.delete(
            "/api/v1/products/{}".format(product["id"]),
            headers=admin_headers,
        )
        self.assertEqual(protected_delete.status_code, 409, protected_delete.text)

    def test_stocktake_count_variance_is_applied_once_and_rejects_stale_stock(self):
        headers = self.setup_admin()
        created = self.client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "name": "کالای شمارش",
                "buy_price": 4,
                "sell_price": 9,
                "track_stock": True,
                "reorder_level": 1,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        product = created.json()
        adjust = self.client.post(
            "/api/v1/inventory/adjustments",
            headers=headers,
            json={"product_id": product["id"], "quantity_change": 10, "reason": "opening"},
        )
        self.assertEqual(adjust.status_code, 201, adjust.text)

        created_take = self.client.post(
            "/api/v1/stocktakes",
            headers=headers,
            json={"name": "انبارگردانی تست", "product_ids": [product["id"]]},
        )
        self.assertEqual(created_take.status_code, 201, created_take.text)
        take = created_take.json()
        self.assertEqual(take["status"], "draft")
        line = take["lines"][0]
        count = self.client.patch(
            "/api/v1/stocktakes/{}/lines/{}".format(take["id"], line["id"]),
            headers=headers,
            json={"counted_quantity": 7},
        )
        self.assertEqual(count.status_code, 200, count.text)
        self.assertEqual(count.json()["lines"][0]["difference"], -3)

        applied = self.client.post(
            "/api/v1/stocktakes/{}/apply".format(take["id"]),
            headers=headers,
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["status"], "applied")
        inventory = self.client.get(
            "/api/v1/inventory?q=کالای شمارش", headers=headers
        ).json()
        self.assertEqual(inventory["items"][0]["stock_quantity"], 7)
        self.assertEqual(
            self.client.post("/api/v1/stocktakes/{}/apply".format(take["id"]), headers=headers).status_code,
            409,
        )

        stale_take = self.client.post(
            "/api/v1/stocktakes",
            headers=headers,
            json={"name": "شمارش قدیمی", "product_ids": [product["id"]]},
        )
        self.assertEqual(stale_take.status_code, 201, stale_take.text)
        stale = stale_take.json()
        self.client.post(
            "/api/v1/inventory/adjustments",
            headers=headers,
            json={"product_id": product["id"], "quantity_change": 1, "reason": "correction"},
        )
        stale_apply = self.client.post(
            "/api/v1/stocktakes/{}/apply".format(stale["id"]), headers=headers
        )
        self.assertEqual(stale_apply.status_code, 409, stale_apply.text)
        current = self.client.get("/api/v1/inventory?q=کالای شمارش", headers=headers).json()
        self.assertEqual(current["items"][0]["stock_quantity"], 8)

    def test_partial_returns_restore_stock_and_post_balanced_journals(self):
        headers = self.setup_admin()
        created = self.client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "name": "کالای مرجوعی",
                "buy_price": 4,
                "sell_price": 10,
                "track_stock": True,
                "reorder_level": 0,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        product = created.json()
        self.client.post(
            "/api/v1/inventory/adjustments",
            headers=headers,
            json={"product_id": product["id"], "quantity_change": 5, "reason": "opening"},
        )

        sale = self.client.post(
            "/api/v1/sales",
            headers=dict(headers, **{"Idempotency-Key": "return-sale-key-001"}),
            json={"items": [{"product_id": product["id"], "quantity": 3}], "paid": True},
        )
        self.assertEqual(sale.status_code, 201, sale.text)
        receipt = sale.json()
        original_line = receipt["items"][0]
        self.assertEqual(original_line["product_name"], "کالای مرجوعی")
        self.assertEqual(original_line["returnable_quantity"], 3)

        returned = self.client.post(
            "/api/v1/returns",
            headers=headers,
            json={
                "receipt_id": receipt["id"],
                "items": [{"original_line_id": original_line["id"], "quantity": 2}],
                "refund_method": "cash",
                "reason": "damaged",
            },
        )
        self.assertEqual(returned.status_code, 201, returned.text)
        self.assertEqual(float(returned.json()["total_amount"]), 20)
        self.assertEqual(returned.json()["items"][0]["quantity"], 2)
        inventory = self.client.get("/api/v1/inventory?q=کالای مرجوعی", headers=headers).json()
        self.assertEqual(inventory["items"][0]["stock_quantity"], 4)

        too_many = self.client.post(
            "/api/v1/returns",
            headers=headers,
            json={
                "receipt_id": receipt["id"],
                "items": [{"original_line_id": original_line["id"], "quantity": 2}],
            },
        )
        self.assertEqual(too_many.status_code, 409, too_many.text)

        journals = self.client.get("/api/v1/journals?page=1&page_size=25", headers=headers)
        self.assertEqual(journals.status_code, 200, journals.text)
        entries = journals.json()
        self.assertGreaterEqual(int(journals.headers.get("X-Total-Count", len(entries))), 2)
        self.assertTrue(all(float(item["debit_total"]) == float(item["credit_total"]) for item in entries))

    def test_optional_product_image_is_stored_and_served_from_private_server_storage(self):
        headers = self.setup_admin()
        created = self.client.post(
            "/api/v1/products",
            headers=headers,
            json={"name": "کالای تصویری", "buy_price": 5, "sell_price": 12,
                  "track_stock": False, "reorder_level": 0},
        )
        self.assertEqual(created.status_code, 201, created.text)
        product_id = created.json()["id"]
        png_signature = b"\x89PNG\r\n\x1a\n"
        uploaded = self.client.post(
            "/api/v1/products/{}/image".format(product_id),
            headers=headers,
            files={"file": ("item.png", png_signature, "image/png")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        image_name = uploaded.json()["image_path"]
        self.assertTrue(image_name.endswith(".png"))
        fetched = self.client.get(
            "/api/v1/products/{}/image".format(product_id), headers=headers
        )
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.headers.get("content-type"), "image/png")
        self.assertEqual(fetched.content, png_signature)
        oversized = self.client.post(
            "/api/v1/products/{}/image".format(product_id),
            headers=headers,
            files={"file": ("bad.png", b"not a png", "image/png")},
        )
        self.assertEqual(oversized.status_code, 415, oversized.text)

    def test_purchase_invoice_weighted_average_supplier_payment_and_expense_journals(self):
        headers = self.setup_admin()
        created = self.client.post(
            "/api/v1/products",
            headers=headers,
            json={"name": "قهوه", "buy_price": 10, "sell_price": 30,
                  "track_stock": True, "reorder_level": 1},
        )
        self.assertEqual(created.status_code, 201, created.text)
        product = created.json()
        adjust = self.client.post(
            "/api/v1/inventory/adjustments", headers=headers,
            json={"product_id": product["id"], "quantity_change": 10, "reason": "opening"},
        )
        self.assertEqual(adjust.status_code, 201, adjust.text)

        supplier_response = self.client.post(
            "/api/v1/partners", headers=headers,
            json={"partner_type": "supplier", "name": "تأمین‌کننده تست"},
        )
        self.assertEqual(supplier_response.status_code, 201, supplier_response.text)
        supplier = supplier_response.json()

        invoice_response = self.client.post(
            "/api/v1/purchase-invoices", headers=headers,
            json={
                "supplier_id": supplier["id"],
                "invoice_number": "SUP-INV-001",
                "invoice_date": "2026-10-29",
                "due_date": "2026-11-10",
                "items": [{
                    "product_id": product["id"], "description": "",
                    "quantity": 5, "unit_cost": 20,
                }],
            },
        )
        self.assertEqual(invoice_response.status_code, 201, invoice_response.text)
        invoice = invoice_response.json()
        self.assertEqual(float(invoice["total_amount"]), 100)
        inventory = self.client.get("/api/v1/products?q=قهوه", headers=headers).json()
        self.assertEqual(float(inventory[0]["stock_quantity"]), 15)
        self.assertAlmostEqual(float(inventory[0]["buy_price"]), 13.3333, places=3)

        payment_response = self.client.post(
            "/api/v1/purchase-invoices/{}/payments".format(invoice["id"]),
            headers=headers,
            json={"amount": 50, "paid_on": "2026-10-29", "payment_method": "bank_transfer"},
        )
        self.assertEqual(payment_response.status_code, 201, payment_response.text)
        self.assertEqual(payment_response.json()["status"], "partial")
        self.assertEqual(float(payment_response.json()["outstanding_amount"]), 50)

        expense_response = self.client.post(
            "/api/v1/expenses", headers=headers,
            json={
                "description": "هزینه برق", "category": "utilities",
                "expense_date": "2026-10-29", "amount": 15,
                "payment_method": "cash",
            },
        )
        self.assertEqual(expense_response.status_code, 201, expense_response.text)
        self.assertEqual(float(expense_response.json()["amount"]), 15)
        journals = self.client.get("/api/v1/journals?page=1&page_size=100", headers=headers)
        self.assertEqual(journals.status_code, 200, journals.text)
        self.assertGreaterEqual(int(journals.headers.get("X-Total-Count", "0")), 3)
        self.assertTrue(all(
            float(item["debit_total"]) == float(item["credit_total"])
            for item in journals.json()
        ))

    def test_kiosk_allowlist_seat_requirement_and_recent_receipts(self):
        admin_headers = self.setup_admin()
        allowed_response = self.client.post(
            "/api/v1/products", headers=admin_headers,
            json={"name": "محصول کیوسک مجاز", "buy_price": 10, "sell_price": 25, "track_stock": False},
        )
        denied_response = self.client.post(
            "/api/v1/products", headers=admin_headers,
            json={"name": "محصول غیرمجاز", "buy_price": 15, "sell_price": 40, "track_stock": False},
        )
        self.assertEqual(allowed_response.status_code, 201, allowed_response.text)
        self.assertEqual(denied_response.status_code, 201, denied_response.text)
        allowed_id = allowed_response.json()["id"]
        denied_id = denied_response.json()["id"]

        saved = self.client.put(
            "/api/v1/kiosk/settings",
            headers=admin_headers,
            json={
                "active": True,
                "allowed_product_ids": [allowed_id],
                "receipt_history_hours": 48,
                "cafe_seat_selection": True,
                "allow_unpaid_orders": True,
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["allowed_product_ids"], [allowed_id])

        kiosk_user = self.client.post(
            "/api/v1/users", headers=admin_headers,
            json={
                "username": "kiosk_test",
                "password": "kiosk-test-password",
                "is_admin": False,
                "buttons": "role:kiosk;products:r;categories:r;sales:c;receipts:r;invoices:r;kiosk:r",
                "is_active": True,
                "requires_session_activation": False,
            },
        )
        self.assertEqual(kiosk_user.status_code, 201, kiosk_user.text)
        login = self.client.post(
            "/api/v1/auth/login",
            json={"username": "kiosk_test", "password": "kiosk-test-password"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        kiosk_headers = {"Authorization": "Bearer " + login.json()["access_token"]}

        catalog = self.client.get("/api/v1/products?page=1&page_size=100", headers=kiosk_headers)
        self.assertEqual(catalog.status_code, 200, catalog.text)
        self.assertEqual([item["id"] for item in catalog.json()], [allowed_id])
        config = self.client.get("/api/v1/kiosk/config", headers=kiosk_headers)
        self.assertEqual(config.status_code, 200, config.text)
        self.assertTrue(config.json()["active"])

        missing_seat = self.client.post(
            "/api/v1/sales/quote", headers=kiosk_headers,
            json={"items": [{"product_id": allowed_id, "quantity": 1}], "paid": False},
        )
        self.assertEqual(missing_seat.status_code, 422, missing_seat.text)
        valid_quote = self.client.post(
            "/api/v1/sales/quote", headers=kiosk_headers,
            json={
                "items": [{"product_id": allowed_id, "quantity": 1}],
                "paid": False, "seat_number": "4",
            },
        )
        self.assertEqual(valid_quote.status_code, 200, valid_quote.text)

        forbidden_quote = self.client.post(
            "/api/v1/sales/quote", headers=kiosk_headers,
            json={
                "items": [{"product_id": denied_id, "quantity": 1}],
                "paid": False, "seat_number": "4",
            },
        )
        self.assertEqual(forbidden_quote.status_code, 403, forbidden_quote.text)

        sale = self.client.post(
            "/api/v1/sales",
            headers=dict(kiosk_headers, **{"Idempotency-Key": "kiosk-seat-sale-001"}),
            json={
                "items": [{"product_id": allowed_id, "quantity": 1}],
                "paid": False, "seat_number": "4",
            },
        )
        self.assertEqual(sale.status_code, 201, sale.text)
        self.assertEqual(sale.json()["seat_number"], "4")

        recent = self.client.get(
            "/api/v1/sales/recent-receipts?page=1&page_size=25", headers=kiosk_headers
        )
        self.assertEqual(recent.status_code, 200, recent.text)
        self.assertGreaterEqual(int(recent.headers.get("X-Total-Count", "0")), 1)
        self.assertEqual(recent.json()[0]["seat_number"], "4")
        self.assertFalse(recent.json()[0]["payed"])

    def test_recent_receipt_search_filters_by_number_seat_name_and_payment(self):
        headers = self.setup_admin()
        product_response = self.client.post(
            "/api/v1/products", headers=headers,
            json={"name": "Tea Search Term", "buy_price": 1, "sell_price": 3.5},
        )
        self.assertEqual(product_response.status_code, 201, product_response.text)
        product = product_response.json()
        sale_response = self.client.post(
            "/api/v1/sales",
            headers=dict(headers, **{"Idempotency-Key": "recent-receipt-search-001"}),
            json={
                "items": [{"product_id": product["id"], "quantity": 1}],
                "paid": False,
                "seat_number": "TABLE-17",
            },
        )
        self.assertEqual(sale_response.status_code, 201, sale_response.text)
        receipt = sale_response.json()

        for query in (
            str(receipt["day_receipt_id"]),
            "TABLE-17",
            "Tea Search Term",
            "پرداخت‌نشده",
        ):
            with self.subTest(query=query):
                response = self.client.get(
                    "/api/v1/sales/recent-receipts",
                    headers=headers,
                    params={"q": query, "page": 1, "page_size": 25},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn(receipt["id"], [row["id"] for row in response.json()])

    def test_recent_receipt_search_filters_by_number_seat_name_and_payment(self):
        headers = self.setup_admin()
        product_response = self.client.post(
            "/api/v1/products", headers=headers,
            json={"name": "Tea Search Term", "buy_price": 1, "sell_price": 3.5},
        )
        self.assertEqual(product_response.status_code, 201, product_response.text)
        product = product_response.json()
        sale_response = self.client.post(
            "/api/v1/sales",
            headers=dict(headers, **{"Idempotency-Key": "recent-receipt-search-001"}),
            json={
                "items": [{"product_id": product["id"], "quantity": 1}],
                "paid": False,
                "seat_number": "TABLE-17",
            },
        )
        self.assertEqual(sale_response.status_code, 201, sale_response.text)
        receipt = sale_response.json()

        for query in (
            str(receipt["day_receipt_id"]),
            "TABLE-17",
            "Tea Search Term",
            "پرداخت‌نشده",
        ):
            with self.subTest(query=query):
                response = self.client.get(
                    "/api/v1/sales/recent-receipts",
                    headers=headers,
                    params={"q": query, "page": 1, "page_size": 25},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn(receipt["id"], [row["id"] for row in response.json()])

    def test_product_creator_can_upload_image_without_update_permission(self):
        admin_headers = self.setup_admin()
        created_user = self.client.post(
            "/api/v1/users", headers=admin_headers,
            json={
                "username": "image_creator",
                "password": "image-creator-password",
                "is_admin": False,
                "buttons": "role:custom;products:c",
                "is_active": True,
                "requires_session_activation": False,
            },
        )
        self.assertEqual(created_user.status_code, 201, created_user.text)
        login = self.client.post(
            "/api/v1/auth/login",
            json={"username": "image_creator", "password": "image-creator-password"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        creator_headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        product = self.client.post(
            "/api/v1/products", headers=creator_headers,
            json={"name": "تصویر بدون مجوز ویرایش", "buy_price": 5, "sell_price": 10},
        )
        self.assertEqual(product.status_code, 201, product.text)
        png_signature = b"\x89PNG\r\n\x1a\n"
        uploaded = self.client.post(
            "/api/v1/products/{}/image".format(product.json()["id"]),
            headers=creator_headers,
            files={"file": ("item.png", png_signature, "image/png")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)

    def test_custom_fields_are_returned_as_table_columns_in_batches(self):
        admin_headers = self.setup_admin()
        product_response = self.client.post(
            "/api/v1/products",
            headers=admin_headers,
            json={"name": "کالای دارای بارکد", "buy_price": 20, "sell_price": 30},
        )
        self.assertEqual(product_response.status_code, 201, product_response.text)
        product = product_response.json()

        definition = self.client.post(
            "/api/v1/schemas/fields",
            headers=admin_headers,
            json={
                "rows": [{
                    "model_key": "products",
                    "model_label": "محصولات",
                    "field_key": "barcode",
                    "field_label": "بارکد",
                    "field_type": "text",
                    "is_required": False,
                }]
            },
        )
        self.assertEqual(definition.status_code, 200, definition.text)
        stored = self.client.patch(
            "/api/v1/schemas/values/products/{}".format(product["id"]),
            headers=admin_headers,
            json={"values": {"barcode": "ABC-123"}},
        )
        self.assertEqual(stored.status_code, 200, stored.text)

        table = self.client.get(
            "/api/v1/schemas/table/products",
            params=[("record_ids", product["id"])],
            headers=admin_headers,
        )
        self.assertEqual(table.status_code, 200, table.text)
        self.assertEqual(
            next(field["label"] for field in table.json()["fields"] if field["key"] == "barcode"),
            "بارکد",
        )
        self.assertEqual(table.json()["values"][product["id"]]["barcode"], "ABC-123")

    def test_resource_permissions_are_enforced_per_operation(self):
        admin_headers = self.setup_admin()
        created = self.client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "username": "readonly_user",
                "password": "read-only-password",
                "is_admin": False,
                "buttons": "role:custom;products:r;warehouse:r;invoices:r",
                "requires_session_activation": False,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        login = self.client.post(
            "/api/v1/auth/login",
            json={"username": "readonly_user", "password": "read-only-password"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}

        self.assertEqual(self.client.get("/api/v1/products", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/inventory", headers=headers).status_code, 200)
        denied_create = self.client.post(
            "/api/v1/products",
            headers=headers,
            json={"name": "رد شده", "buy_price": 1, "sell_price": 2},
        )
        self.assertEqual(denied_create.status_code, 403)
        denied_adjustment = self.client.post(
            "/api/v1/inventory/adjustments",
            headers=headers,
            json={"product_id": "00000000-0000-0000-0000-000000000001", "quantity_change": 1},
        )
        self.assertEqual(denied_adjustment.status_code, 403)
        self.assertEqual(
            self.client.get("/api/v1/invoices/template", headers=headers).status_code, 200
        )
        denied_template_update = self.client.put(
            "/api/v1/invoices/template",
            headers=headers,
            json={"company_name": "نباید ذخیره شود"},
        )
        self.assertEqual(denied_template_update.status_code, 403)

    def test_remote_first_run_requires_a_separate_bootstrap_token(self):
        request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.10"))
        payload = SetupRequest(
            username="admin1",
            password="correct horse",
            password_confirmation="correct horse",
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ACCOUNTING_APP_SETUP_TOKEN", None)
            with self.assertRaises(HTTPException) as denied:
                _authorize_setup(request, payload)
            self.assertEqual(denied.exception.status_code, 403)

        with patch.dict(os.environ, {"ACCOUNTING_APP_SETUP_TOKEN": "separate-setup-secret"}):
            with self.assertRaises(HTTPException):
                _authorize_setup(request, payload)
            authorized = SetupRequest(
                username="admin1",
                password="correct horse",
                password_confirmation="correct horse",
                setup_token="separate-setup-secret",
            )
            _authorize_setup(request, authorized)


if __name__ == "__main__":
    unittest.main()
