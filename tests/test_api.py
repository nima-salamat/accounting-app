"""End-to-end tests for the FastAPI boundary using a temporary SQLite database."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("ACCOUNTING_APP_SECRET_KEY", "test-signing-key-with-more-than-32-characters")

from fastapi.testclient import TestClient

from accounting_app.database.connection import DBManager, db, initialize_db
from accounting_app.database.models import Product, Receipt
from manager.db import create_db
from server.app.main import app


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
            json={"username": "cashier", "password": "cashier-password", "is_admin": False},
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


if __name__ == "__main__":
    unittest.main()
