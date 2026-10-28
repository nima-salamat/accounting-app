"""Regression tests for drag-and-drop invoice geometry and sheet dimensions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from PySide6.QtWidgets import QApplication

from client.ui.invoice_render import DEFAULT_TEMPLATE, default_elements_for_paper, normalize_elements, page_dimensions
from client.ui.invoice_templates_page import InvoiceTemplatesPage


class _WindowStub:
    def __init__(self):
        self.current_user = {"username": "designer-test", "is_admin": True}
        self.api = None
        self.status = ""

    def show_error(self, error):
        self.status = str(error)

    def set_status(self, message):
        self.status = str(message)


class InvoiceDesignerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = _WindowStub()
        self.page = InvoiceTemplatesPage(self.window)

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        self.app.processEvents()

    def test_default_invoice_number_and_date_share_header_row(self):
        elements = {item["id"]: item for item in normalize_elements(DEFAULT_TEMPLATE["elements"], DEFAULT_TEMPLATE)}
        self.assertEqual(elements["invoice_number"]["y_mm"], elements["invoice_date"]["y_mm"])
        self.assertLess(elements["invoice_date"]["x_mm"], elements["invoice_number"]["x_mm"])
        self.assertEqual(elements["invoice_date"]["align"], "left")
        self.assertEqual(elements["invoice_number"]["align"], "right")

    def test_orientation_and_paper_size_change_the_actual_canvas(self):
        self.assertEqual(page_dimensions(self.page._values()), (210.0, 297.0))
        self.page.orientation.setCurrentIndex(self.page.orientation.findData("landscape"))
        self.assertEqual(page_dimensions(self.page._values()), (297.0, 210.0))
        self.assertEqual(self.page.scene.sceneRect().width(), 297.0)
        self.assertIn("افقی", self.page.page_info.text())
        self.page.paper_size.setCurrentIndex(self.page.paper_size.findData("A5"))
        self.assertEqual(page_dimensions(self.page._values()), (210.0, 148.0))
        self.assertIn("A5", self.page.page_info.text())

    def test_dragged_element_coordinates_are_saved_in_the_template(self):
        item = self.page._items_by_id["invoice_number"]
        item.setSelected(True)
        item.setPos(134, 18)
        element = next(value for value in self.page._values()["elements"] if value["id"] == "invoice_number")
        self.assertAlmostEqual(element["x_mm"], item.pos().x())
        self.assertAlmostEqual(element["y_mm"], item.pos().y())
        self.assertAlmostEqual(element["x_mm"], 134)
        self.assertAlmostEqual(element["y_mm"], 18)

    def test_presets_change_both_paper_and_layout(self):
        self.page.preset.setCurrentIndex(self.page.preset.findData("thermal80"))
        self.page.apply_preset()
        self.assertEqual(self.page.paper_size.currentData(), "receipt80")
        self.assertEqual(page_dimensions(self.page._values()), (80.0, 220.0))
        self.assertTrue(any(item["type"] == "items_table" for item in self.page._values()["elements"]))
        self.assertIn("۸۰ میلی‌متر", self.page.page_info.text())

    def test_custom_elements_can_be_added_duplicated_and_removed(self):
        before = len(self.page._values()["elements"])
        self.page.new_kind.setCurrentIndex(self.page.new_kind.findData("text"))
        self.page.add_element()
        self.assertEqual(len(self.page._values()["elements"]), before + 1)
        self.page.duplicate_element()
        self.assertEqual(len(self.page._values()["elements"]), before + 2)
        self.page.delete_element()
        self.assertEqual(len(self.page._values()["elements"]), before + 1)


if __name__ == "__main__":
    unittest.main()
