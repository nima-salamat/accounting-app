"""Regression tests for the optional product-image upload workflow."""

import unittest

from client.ui.data_pages import ProductsPage


class _FakeApi:
    def __init__(self, *, upload_error=None):
        self.upload_error = upload_error or RuntimeError("403: image upload is not permitted")
        self.created_values = None
        self.updated_values = None
        self.upload_calls = []

    def create_product(self, **values):
        self.created_values = dict(values)
        return {"id": "product-1", **values}

    def update_product(self, product_id, **values):
        self.updated_values = (product_id, dict(values))
        return {"id": product_id, "name": values.get("name", "Existing product")}

    def upload_product_image(self, product_id, path):
        self.upload_calls.append((product_id, path))
        if self.upload_error:
            raise self.upload_error
        return {"image_path": path}


class ProductImageWorkflowTests(unittest.TestCase):
    def test_failed_image_upload_keeps_the_created_product_result(self):
        api = _FakeApi()
        result = ProductsPage._create_product(
            api,
            {"name": "Tea", "sell_price": 2, "image_file": "/tmp/tea.png"},
        )

        self.assertEqual(result["id"], "product-1")
        self.assertEqual(result["name"], "Tea")
        self.assertIn("403", result["_image_upload_error"])
        self.assertEqual(api.created_values, {"name": "Tea", "sell_price": 2})
        self.assertEqual(api.upload_calls, [("product-1", "/tmp/tea.png")])

    def test_failed_image_upload_keeps_the_updated_product_result(self):
        api = _FakeApi()
        result = ProductsPage._update_product(
            api,
            "product-9",
            {"name": "Updated tea", "image_file": "/tmp/updated.png"},
        )

        self.assertEqual(result["id"], "product-9")
        self.assertEqual(result["name"], "Updated tea")
        self.assertIn("403", result["_image_upload_error"])
        self.assertEqual(api.updated_values, ("product-9", {"name": "Updated tea"}))

    def test_product_without_new_image_does_not_attempt_upload(self):
        api = _FakeApi()
        result = ProductsPage._create_product(api, {"name": "Tea", "sell_price": 2})

        self.assertEqual(result["name"], "Tea")
        self.assertNotIn("_image_upload_error", result)
        self.assertEqual(api.upload_calls, [])


if __name__ == "__main__":
    unittest.main()
