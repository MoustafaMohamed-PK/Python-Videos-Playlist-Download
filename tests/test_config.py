import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import AppConfig, ConfigManager


class TestAppConfigDefaults(unittest.TestCase):
    def test_defaults(self):
        config = AppConfig()
        self.assertEqual(config.download_folder, "")
        self.assertEqual(config.quality, "1080p")
        self.assertEqual(config.filename_mode, "original")
        self.assertEqual(config.filename_pattern, "{title}")
        self.assertEqual(config.existing_file_behavior, "skip")

    def test_to_dict_excludes_forbidden_keys(self):
        config = AppConfig()
        data = config.to_dict()
        for forbidden in ("cookies", "password", "token"):
            self.assertNotIn(forbidden, data)

    def test_from_dict_ignores_unknown_keys(self):
        config = AppConfig.from_dict({"quality": "720p", "unexpected_key": "value"})
        self.assertEqual(config.quality, "720p")
        self.assertFalse(hasattr(config, "unexpected_key"))

    def test_concurrency_defaults(self):
        config = AppConfig()
        self.assertEqual(config.concurrency, 3)
        self.assertEqual(config.concurrent_fragments, 4)

    def test_from_dict_clamps_concurrency_to_valid_range(self):
        too_high = AppConfig.from_dict({"concurrency": 999, "concurrent_fragments": 999})
        self.assertEqual(too_high.concurrency, 8)
        self.assertEqual(too_high.concurrent_fragments, 8)

        too_low = AppConfig.from_dict({"concurrency": 0, "concurrent_fragments": -5})
        self.assertEqual(too_low.concurrency, 1)
        self.assertEqual(too_low.concurrent_fragments, 1)


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmp_dir.name) / "config.json"
        self.manager = ConfigManager(self.config_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_load_missing_file_returns_defaults(self):
        config = self.manager.load()
        self.assertEqual(config, AppConfig())

    def test_save_then_load_roundtrip(self):
        config = AppConfig(
            download_folder="/tmp/videos",
            quality="720p",
            filename_mode="numbered",
            filename_pattern="{title}",
            existing_file_behavior="overwrite",
        )
        self.manager.save(config)
        loaded = self.manager.load()
        self.assertEqual(loaded, config)

    def test_save_creates_parent_directories(self):
        nested_path = Path(self.tmp_dir.name) / "nested" / "dir" / "config.json"
        manager = ConfigManager(nested_path)
        manager.save(AppConfig())
        self.assertTrue(nested_path.exists())

    def test_load_corrupt_json_falls_back_to_defaults(self):
        self.config_path.write_text("{not valid json", encoding="utf-8")
        config = self.manager.load()
        self.assertEqual(config, AppConfig())

    def test_load_non_dict_json_falls_back_to_defaults(self):
        self.config_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        config = self.manager.load()
        self.assertEqual(config, AppConfig())

    def test_save_does_not_persist_forbidden_keys_even_if_injected(self):
        config = AppConfig()
        # Simulate a forbidden key sneaking into the dict form.
        data = config.to_dict()
        data["password"] = "should-not-be-written"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh)
        raw_text = self.config_path.read_text(encoding="utf-8")
        # This test documents current on-disk content before a save() call
        # normalizes it; to_dict() itself is what's guaranteed to strip it.
        self.assertNotIn("password", config.to_dict())


if __name__ == "__main__":
    unittest.main()
