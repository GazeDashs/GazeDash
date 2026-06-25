import json
import tempfile
import unittest
from pathlib import Path

from core.gesture_engine.gesture_diagnostics_logger import GestureDiagnosticsLogger


class GestureDiagnosticsLoggerTests(unittest.TestCase):
    def test_writes_jsonl_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = GestureDiagnosticsLogger(
                enabled=True,
                log_dir=tmp,
                min_interval_seconds=0.0,
                only_log_changes=False,
                component="test",
            )
            debug = {
                "reason": "ok",
                "raw_active": ["mouth_open", "mouth_o"],
                "active": ["mouth_o"],
                "groups": {
                    "mouth": {
                        "candidates": ["mouth_open", "mouth_o"],
                        "candidate": "mouth_o",
                        "active": "mouth_o",
                        "rejected": ["mouth_open"],
                    }
                },
                "ungrouped": [],
            }

            self.assertTrue(logger.record(debug, profile_name="juego_simple", detected_gesture="mouth_o"))
            logger.close()

            files = list(Path(tmp).glob("gesture_diagnostics_test_*.jsonl"))
            self.assertEqual(len(files), 1)
            lines = files[0].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)

            event = json.loads(lines[0])
            self.assertEqual(event["component"], "test")
            self.assertEqual(event["profile"], "juego_simple")
            self.assertEqual(event["detected_gesture"], "mouth_o")
            self.assertEqual(event["debug"]["active"], ["mouth_o"])

    def test_disabled_logger_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = GestureDiagnosticsLogger(enabled=False, log_dir=tmp, component="test")

            self.assertFalse(logger.record({"reason": "ok", "raw_active": [], "active": []}))
            logger.close()

            self.assertEqual(list(Path(tmp).glob("*.jsonl")), [])

    def test_from_config_reads_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = GestureDiagnosticsLogger.from_config(
                {
                    "gesture_diagnostics": {
                        "enabled": True,
                        "log_dir": tmp,
                        "min_interval_seconds": 0.75,
                        "only_log_changes": False,
                    }
                },
                component="test",
            )

            try:
                self.assertTrue(logger.enabled)
                self.assertEqual(logger.log_dir, Path(tmp))
                self.assertEqual(logger.min_interval_seconds, 0.75)
                self.assertFalse(logger.only_log_changes)
            finally:
                logger.close()

    def test_invalid_log_dir_disables_logger_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            invalid_dir = Path(tmp) / "not_a_directory"
            invalid_dir.write_text("occupied", encoding="utf-8")

            logger = GestureDiagnosticsLogger(enabled=True, log_dir=invalid_dir, component="test")

            self.assertFalse(logger.enabled)
            self.assertFalse(logger.record({"reason": "ok", "raw_active": ["smile"], "active": ["smile"]}))
            logger.close()


if __name__ == "__main__":
    unittest.main()
