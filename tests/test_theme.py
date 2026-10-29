"""Tests for the shared client typography/design-token configuration."""
import unittest

from client.ui.theme import DEFAULT_DESIGN, normalize_design_config, stylesheet


class ThemeConfigurationTests(unittest.TestCase):
    def test_valid_font_family_and_layout_options_are_kept(self):
        settings = normalize_design_config({
            "font_family": "Noto Sans Arabic", "font_size": 16,
            "heading_scale": 1.2, "density": "spacious", "corner_radius": 14,
        })
        self.assertEqual(settings["font_family"], "Noto Sans Arabic")
        self.assertEqual(settings["font_size"], 16)
        self.assertEqual(settings["density"], "spacious")
        self.assertEqual(settings["corner_radius"], 14)

    def test_unsafe_font_family_falls_back_to_default(self):
        settings = normalize_design_config({"font_family": '"; } QWidget { color:red; /*'})
        self.assertEqual(settings["font_family"], DEFAULT_DESIGN["font_family"])

    def test_numeric_input_selection_text_has_contrast_in_both_themes(self):
        for mode in ("light", "dark"):
            css = stylesheet(mode)
            app_styles = css[css.rfind("QLineEdit, QComboBox, QSpinBox"):]
            self.assertIn("selection-background-color:", app_styles)
            self.assertIn("selection-color: #FFFFFF", app_styles)
            self.assertIn("QAbstractSpinBox QLineEdit", app_styles)

    def test_stylesheet_uses_requested_font_and_density(self):
        qss = stylesheet("dark", {"font_family": "Tahoma", "font_size": 15, "density": "compact"})
        self.assertIn('font-family: "Tahoma"', qss)
        self.assertIn("font-size: 15px", qss)
        self.assertIn("QMenu", qss)

    def test_surface_styles_cover_radio_buttons_lists_and_scroll_areas(self):
        for mode in ("light", "dark"):
            qss = stylesheet(mode)
            self.assertIn("QRadioButton", qss)
            self.assertIn("QListWidget", qss)
            self.assertIn("QAbstractItemView", qss)
            self.assertIn("QScrollBar::handle:vertical", qss)
            self.assertIn("background-color: transparent", qss)

    def test_icon_helper_maps_common_actions_to_semantic_icons(self):
        from client.ui.icons import icon_for_action
        self.assertEqual(icon_for_action("products"), "fa5s.boxes")
        self.assertEqual(icon_for_action("صفحهٔ بعد"), "fa5s.chevron-left")
        self.assertEqual(icon_for_action("افزودن به سبد"), "fa5s.cart-plus")


if __name__ == "__main__":
    unittest.main()
