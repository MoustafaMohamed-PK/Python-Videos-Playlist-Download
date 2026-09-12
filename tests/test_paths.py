import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.paths import resolve_within
from app.validators import ValidationError


class TestResolveWithin(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_empty_relative_returns_root(self):
        self.assertEqual(resolve_within(self.root, None), self.root.resolve())
        self.assertEqual(resolve_within(self.root, ""), self.root.resolve())

    def test_dot_returns_root(self):
        self.assertEqual(resolve_within(self.root, "."), self.root.resolve())

    def test_simple_subfolder_resolves_inside_root(self):
        result = resolve_within(self.root, "my videos")
        self.assertEqual(result, self.root.resolve() / "my videos")

    def test_nested_subfolder_resolves_inside_root(self):
        result = resolve_within(self.root, "a/b/c")
        self.assertEqual(result, self.root.resolve() / "a" / "b" / "c")

    def test_absolute_path_rejected(self):
        with self.assertRaises(ValidationError):
            resolve_within(self.root, "/etc/passwd")

    def test_parent_traversal_is_neutralized_not_honored(self):
        # ".." segments are dropped rather than applied -- this must
        # never let the result climb above root, even into a sibling.
        result = resolve_within(self.root, "../../etc")
        self.assertEqual(result, self.root.resolve() / "etc")
        self.assertTrue(str(result).startswith(str(self.root.resolve())))

    def test_traversal_mixed_with_real_segments_stays_inside(self):
        result = resolve_within(self.root, "foo/../../bar")
        self.assertTrue(str(result).startswith(str(self.root.resolve())))

    def test_backslash_rejected(self):
        with self.assertRaises(ValidationError):
            resolve_within(self.root, "..\\..\\windows")

    def test_null_byte_rejected(self):
        with self.assertRaises(ValidationError):
            resolve_within(self.root, "foo\x00bar")

    def test_symlink_escape_is_rejected(self):
        outside = tempfile.TemporaryDirectory()
        try:
            link = self.root / "escape"
            os.symlink(outside.name, link)
            with self.assertRaises(ValidationError):
                resolve_within(self.root, "escape/secret.txt")
        finally:
            outside.cleanup()

    def test_illegal_filename_characters_are_sanitized(self):
        # Reuses sanitize_filename per component -- must not raise, and
        # must not contain the illegal characters afterward.
        result = resolve_within(self.root, 'weird<>name')
        self.assertTrue(str(result).startswith(str(self.root.resolve())))
        for ch in "<>":
            self.assertNotIn(ch, result.name)


if __name__ == "__main__":
    unittest.main()
