import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import main as app


class AutoRecordingTests(unittest.TestCase):
    def setUp(self):
        self.config = deepcopy(app.DEFAULT_CONFIG)
        self.auto = app.AutoStateMachine(self.config)

    def start(self):
        self.assertFalse(self.auto.maybe_start(59, 9.8, False))
        self.assertFalse(self.auto.maybe_start(58, 9.9, False))
        self.assertTrue(self.auto.maybe_start(58, 10, False))

    def test_start_requires_consecutive_valid_start_readings(self):
        self.assertFalse(self.auto.maybe_start(58, 1, False))
        self.assertFalse(self.auto.maybe_start(None, 2, False))
        self.assertFalse(self.auto.maybe_start(58, 3, False))
        self.assertFalse(self.auto.maybe_start(54, 4, False))
        self.start()
        self.assertEqual(self.auto.deadline, 70)

    def test_duration_ignores_missing_timer_and_end_digits(self):
        self.start()
        for seconds, now in [(1, 11), (0, 12), (0, 13), (0, 14), (None, 20), (None, 69.999)]:
            self.assertIsNone(self.auto.maybe_finish(seconds, now, True, "auto"))
        self.assertEqual(self.auto.maybe_finish(None, 70, True, "auto"), "duration elapsed")
        self.assertEqual(self.auto.remaining(71), 0)

    def test_custom_duration_is_frozen_until_next_recording(self):
        self.config["auto"]["duration_sec"] = 90
        self.start()
        self.config["auto"].update({"duration_sec": 1, "end_mode": "timer"})
        self.assertIsNone(self.auto.maybe_finish(None, 99.9, True, "auto"))
        self.assertEqual(self.auto.maybe_finish(58, 100, True, "auto"), "duration elapsed")

    def test_finished_recording_waits_for_cooldown_and_a_new_start(self):
        self.start()
        self.auto.record_stopped({"grade": "N/A"}, 70)
        self.assertIsNone(self.auto.remaining(71))
        self.assertFalse(self.auto.maybe_start(58, 74.9, False))
        self.assertFalse(self.auto.maybe_start(0, 75, False))
        self.assertFalse(self.auto.maybe_start(58, 76, False))
        self.assertFalse(self.auto.maybe_start(58, 77, False))
        self.assertTrue(self.auto.maybe_start(58, 78, False))
        self.assertEqual(self.auto.deadline, 138)

    def test_timer_mode_preserves_end_detection_and_loss_grace(self):
        self.config["auto"]["end_mode"] = "timer"
        self.start()
        self.assertIsNone(self.auto.remaining(10))
        self.assertIsNone(self.auto.maybe_finish(1, 11, True, "auto"))
        self.assertIsNone(self.auto.maybe_finish(0, 12, True, "auto"))
        self.assertEqual(self.auto.maybe_finish(0, 13, True, "auto"), "timer end")
        self.assertIsNone(self.auto.maybe_finish(None, 15, True, "auto"))
        self.assertEqual(self.auto.maybe_finish(None, 15.01, True, "auto"), "timer lost")

    def test_manual_and_disabled_recordings_are_never_timed_out(self):
        self.assertFalse(self.auto.maybe_start(58, 1, True))
        self.start()
        self.assertIsNone(self.auto.maybe_finish(None, 70, True, "manual"))
        self.assertIsNone(self.auto.maybe_finish(None, 70, False, None))
        self.config["auto"]["enabled"] = False
        self.assertIsNone(self.auto.maybe_finish(None, 70, True, "auto"))

    def test_existing_config_gets_the_new_60_second_default(self):
        legacy = deepcopy(self.config)
        legacy["auto"].pop("end_mode")
        legacy["auto"].pop("duration_sec")
        checked, warnings = app.validate_config(legacy)
        self.assertFalse(warnings)
        self.assertEqual(checked["auto"]["end_mode"], "duration")
        self.assertEqual(checked["auto"]["duration_sec"], 60)

    def test_duration_and_mode_validation_and_save_load(self):
        for value in [0, -1, "", "abc", 1.5, "NaN", float("inf"), 3601, None]:
            with self.subTest(value=value):
                checked, warnings = app.validate_config({"auto": {"duration_sec": value}})
                self.assertTrue(warnings)
                self.assertEqual(checked["auto"]["duration_sec"], 60)
        checked, warnings = app.validate_config({"auto": {"end_mode": "unknown"}})
        self.assertTrue(warnings)
        self.assertEqual(checked["auto"]["end_mode"], "duration")
        for mode, duration in [("duration", 1), ("timer", 3600), ("duration", "120")]:
            checked, warnings = app.validate_config({"auto": {"end_mode": mode, "duration_sec": duration}})
            self.assertFalse(warnings)
            with tempfile.TemporaryDirectory() as folder, patch.object(app, "CONFIG_FILE", str(Path(folder) / "config.json")):
                app.save_config(checked)
                loaded, warnings = app.load_config()
            self.assertFalse(warnings)
            self.assertEqual(loaded["auto"]["end_mode"], mode)
            self.assertEqual(loaded["auto"]["duration_sec"], int(duration))


if __name__ == "__main__":
    unittest.main()
