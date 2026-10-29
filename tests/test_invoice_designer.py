"""Regression tests for drag-and-drop invoice geometry and sheet dimensions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QGraphicsLineItem, QSpinBox

from client.ui.invoice_render import DEFAULT_TEMPLATE, default_elements_for_paper, normalize_elements, page_dimensions
from client.ui.invoice_templates_page import InvoiceTemplatesPage
from client.ui.theme import install_spinbox_wheel_guard


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

    def test_document_kind_and_preset_menus_keep_a_readable_minimum_width(self):
        self.assertEqual(self.page.document_kind.objectName(), "InvoiceDocumentKind")
        self.assertGreaterEqual(self.page.document_kind.minimumWidth(), 210)
        self.assertGreaterEqual(self.page.preset.minimumWidth(), 240)
        self.assertGreaterEqual(self.page.paper_size.minimumWidth(), 185)
        self.assertEqual(self.page.document_kind.count(), 5)
        self.assertEqual(self.page.preset.count(), 7)

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

    def test_drag_snap_aligns_edges_and_centers_on_both_axes(self):
        elements = [
            {
                "id": "anchor", "type": "text", "label": "مرجع",
                "text": "مرجع", "x_mm": 30, "y_mm": 30, "w_mm": 50, "h_mm": 10,
                "font_size": 9, "align": "right", "bold": False, "visible": True,
            },
            {
                "id": "moving", "type": "text", "label": "متحرک",
                "text": "متحرک", "x_mm": 100, "y_mm": 60, "w_mm": 20, "h_mm": 12,
                "font_size": 9, "align": "right", "bold": False, "visible": True,
            },
        ]
        self.page._load_template({**DEFAULT_TEMPLATE, "elements": elements})
        moving = self.page._items_by_id["moving"]

        # The proposed left/top edges are close to the reference's right/bottom edges.
        snapped = self.page._snap_item_position(moving, QPointF(77.0, 38.0))
        self.assertAlmostEqual(snapped.x(), 80.0)
        self.assertAlmostEqual(snapped.y(), 40.0)
        self.assertEqual(len(self.page.scene._alignment_guide_items), 2)
        self.assertIn("راهنمای هوشمند فعال", self.page.canvas_help.text())

        self.page.scene.clear_alignment_guides()
        self.page._reset_alignment_hint()
        self.assertEqual(self.page.scene._alignment_guide_items, [])
        self.assertEqual(self.page.canvas_help.text(), self.page._alignment_hint_default)

    def test_drag_snap_can_preserve_equal_horizontal_spacing(self):
        elements = [
            {
                "id": "first", "type": "text", "label": "اول",
                "text": "اول", "x_mm": 20, "y_mm": 20, "w_mm": 20, "h_mm": 12,
                "font_size": 9, "align": "right", "bold": False, "visible": True,
            },
            {
                "id": "second", "type": "text", "label": "دوم",
                "text": "دوم", "x_mm": 60, "y_mm": 20, "w_mm": 20, "h_mm": 12,
                "font_size": 9, "align": "right", "bold": False, "visible": True,
            },
            {
                "id": "moving", "type": "text", "label": "متحرک",
                "text": "متحرک", "x_mm": 98, "y_mm": 22, "w_mm": 10, "h_mm": 10,
                "font_size": 9, "align": "right", "bold": False, "visible": True,
            },
        ]
        self.page._load_template({**DEFAULT_TEMPLATE, "elements": elements})
        moving = self.page._items_by_id["moving"]
        snapped = self.page._snap_item_position(moving, QPointF(98.0, 22.0))
        self.assertAlmostEqual(snapped.x(), 100.0)
        self.assertTrue(any(
            isinstance(guide, QGraphicsLineItem)
            for guide in self.page.scene._alignment_guide_items
        ))
        self.assertIn("فاصلهٔ افقی برابر", self.page.canvas_help.text())

    def test_snap_does_not_move_elements_when_no_alignment_is_close(self):
        elements = [
            {
                "id": "anchor", "type": "text", "label": "مرجع",
                "text": "مرجع", "x_mm": 20, "y_mm": 20, "w_mm": 30, "h_mm": 12,
                "font_size": 9, "align": "right", "bold": False, "visible": True,
            },
            {
                "id": "moving", "type": "text", "label": "متحرک",
                "text": "متحرک", "x_mm": 100, "y_mm": 100, "w_mm": 20, "h_mm": 12,
                "font_size": 9, "align": "right", "bold": False, "visible": True,
            },
        ]
        self.page._load_template({**DEFAULT_TEMPLATE, "elements": elements})
        moving = self.page._items_by_id["moving"]
        proposed = QPointF(100.0, 100.0)
        snapped = self.page._snap_item_position(moving, proposed)
        self.assertAlmostEqual(snapped.x(), proposed.x())
        self.assertAlmostEqual(snapped.y(), proposed.y())
        self.assertEqual(self.page.scene._alignment_guide_items, [])

    def test_presets_change_both_paper_and_layout(self):
        self.page.preset.setCurrentIndex(self.page.preset.findData("thermal80"))
        self.page.apply_preset()
        self.assertEqual(self.page.paper_size.currentData(), "receipt80")
        self.assertEqual(page_dimensions(self.page._values()), (80.0, 220.0))
        self.assertTrue(any(item["type"] == "items_table" for item in self.page._values()["elements"]))
        self.assertIn("80 × 220", self.page.page_info.text())

    def test_zoom_buttons_and_canvas_preserve_manual_navigation_until_fit(self):
        initial_scale = self.page.canvas.transform().m11()
        self.page.canvas.zoom_by(1.25)
        self.assertGreater(self.page.canvas.transform().m11(), initial_scale)
        self.assertTrue(self.page.canvas._user_zoomed)
        self.page._fit_page(force=True)
        self.assertFalse(self.page.canvas._user_zoomed)

    def test_mouse_wheel_does_not_change_any_spinbox_value(self):
        install_spinbox_wheel_guard(self.app)
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setValue(17)
        point = QPointF(5, 5)
        wheel = QWheelEvent(
            point, point, QPoint(0, 0), QPoint(0, 120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate, False,
        )
        self.app.sendEvent(spin, wheel)
        self.assertEqual(spin.value(), 17)
        spin.close()

    def test_document_profiles_select_different_default_paper_sizes(self):
        self.page.document_kind.setCurrentIndex(self.page.document_kind.findData("pos_receipt"))
        self.assertEqual(self.page._template_kind, "pos_receipt")
        self.assertEqual(self.page.paper_size.currentData(), "receipt80")
        self.page.document_kind.setCurrentIndex(self.page.document_kind.findData("return_slip"))
        self.assertEqual(self.page._template_kind, "return_slip")
        self.assertEqual(self.page.paper_size.currentData(), "A5")

    def test_numbering_metadata_is_preserved_without_designer_controls(self):
        self.assertFalse(hasattr(self.page, "invoice_number_card"))
        for name in (
            "invoice_number_style", "invoice_number_prefix",
            "invoice_number_date_format", "invoice_number_separator",
            "invoice_number_padding", "invoice_number_custom_format",
        ):
            self.assertFalse(hasattr(self.page, name), name)

        self.page._load_template({
            **DEFAULT_TEMPLATE,
            "invoice_number_format": "{SEQ}",
            "invoice_number_padding": 7,
        })
        values = self.page._values()
        self.assertEqual(values["invoice_number_format"], "{SEQ}")
        self.assertEqual(values["invoice_number_padding"], 7)

        self.page.sync_invoice_numbering("PREFIX-{SEQ}", 6)
        values = self.page._values()
        self.assertEqual(values["invoice_number_format"], "PREFIX-{SEQ}")
        self.assertEqual(values["invoice_number_padding"], 6)

    def test_custom_numbering_pattern_round_trips_without_numbering_ui(self):
        pattern = "2026-{MM}-{D}-NUM-{NUM}"
        self.page._load_template({
            **DEFAULT_TEMPLATE,
            "invoice_number_format": pattern,
            "invoice_number_padding": 4,
        })
        values = self.page._values()
        self.assertEqual(values["invoice_number_format"], pattern)
        self.assertEqual(values["invoice_number_padding"], 4)
        self.assertFalse(hasattr(self.page, "invoice_number_custom_format"))

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
