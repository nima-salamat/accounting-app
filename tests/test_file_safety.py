import os
import tempfile
import unittest
from pathlib import Path

from accounting_app.services.file_safety import is_managed_image_path


class ManagedFilePathTests(unittest.TestCase):
    def test_only_files_inside_images_directory_are_managed(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "images").mkdir()
            (root / "images" / "123e4567-e89b-12d3-a456-426614174000.png").write_bytes(b"image")
            (root / "images" / "personal.png").write_bytes(b"keep")
            (root / "important.txt").write_text("keep", encoding="utf-8")
            try:
                os.chdir(root)
                self.assertTrue(is_managed_image_path("images/123e4567-e89b-12d3-a456-426614174000.png"))
                self.assertFalse(is_managed_image_path("important.txt"))
                self.assertFalse(is_managed_image_path("../important.txt"))
                self.assertFalse(is_managed_image_path("images"))
                self.assertFalse(is_managed_image_path("images/personal.png"))
                self.assertFalse(is_managed_image_path(""))
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
