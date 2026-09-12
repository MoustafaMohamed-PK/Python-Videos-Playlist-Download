import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.validators import (
    ValidationError,
    ensure_writable_directory,
    validate_destination_path,
)


class TestValidateDestinationPath(unittest.TestCase):
    def test_empty_raises(self):
        with self.assertRaises(ValidationError):
            validate_destination_path("")

    def test_strips_surrounding_quotes(self):
        result = validate_destination_path('"/tmp/some folder"')
        self.assertEqual(str(result), "/tmp/some folder")

    def test_handles_spaces_in_path(self):
        result = validate_destination_path("/tmp/My Videos")
        self.assertEqual(str(result), "/tmp/My Videos")

    def test_relative_path_preserved(self):
        result = validate_destination_path("./downloads")
        self.assertEqual(result, Path("./downloads"))

    def test_expands_user_home(self):
        result = validate_destination_path("~/Videos")
        self.assertFalse(str(result).startswith("~"))


class TestEnsureWritableDirectory(unittest.TestCase):
    def test_missing_directory_reports_does_not_exist(self):
        missing = Path(tempfile.gettempdir()) / "ytdl_definitely_missing_dir_xyz"
        if missing.exists():
            missing.rmdir()
        ok, err = ensure_writable_directory(missing)
        self.assertFalse(ok)
        self.assertEqual(err, "does_not_exist")

    def test_existing_writable_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, err = ensure_writable_directory(Path(tmp))
            self.assertTrue(ok)
            self.assertIsNone(err)

    def test_file_instead_of_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "not_a_dir.txt"
            file_path.write_text("hello")
            ok, err = ensure_writable_directory(file_path)
            self.assertFalse(ok)
            self.assertIn("not a directory", err)


if __name__ == "__main__":
    unittest.main()
