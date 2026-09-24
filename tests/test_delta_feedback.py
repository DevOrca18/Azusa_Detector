import math
import unittest
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch

import main as app
from delta_feedback import DEFAULT_DELTA, DeltaFeedback, delta_exceeded, preview_transform


class DeltaFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.config = {**DEFAULT_DELTA, "enabled": True, "x_px": 10.0, "y_px": 15.0}

    def test_axes_use_either_axis_absolute_value_and_inclusive_boundary(self):
        for delta, expected in [((9, 14), False), ((10, 0), True), ((0, -15), True), ((-12, 2), True)]:
            self.assertEqual(delta_exceeded(delta, self.config), expected)

    def test_distance_combines_both_axes(self):
        self.config["method"] = "distance"
        self.assertTrue(delta_exceeded((-6, 8), self.config))
        self.assertFalse(delta_exceeded((6, 7), self.config))
        self.assertTrue(delta_exceeded((0, -10), self.config))

    def test_missing_first_and_disabled_samples_do_not_trigger(self):
        self.assertIsNone(delta_exceeded(None, self.config))
        feedback = DeltaFeedback(self.config)
        self.assertFalse(feedback.update((100, 100), False, 1.0))
        self.assertIsNone(feedback.over_threshold)
        self.config["enabled"] = False
        self.assertIsNone(delta_exceeded((100, 100), self.config))

    def test_sound_is_rate_limited_without_losing_per_frame_threshold_state(self):
        feedback = DeltaFeedback(self.config)
        self.assertTrue(feedback.update((20, 0), True, 1.0))
        self.assertFalse(feedback.update((20, 0), True, 1.1))
        self.assertTrue(feedback.over_threshold)
        self.assertTrue(feedback.visible(1.5))
        self.assertFalse(feedback.visible(1.9))
        self.assertFalse(feedback.update((20, 0), False, 2.1))
        self.assertTrue(feedback.update((-30, 0), True, 3.0))

    def test_disabling_alert_clears_visible_warning_immediately(self):
        feedback = DeltaFeedback(self.config)
        feedback.update((20, 0), True, 1.0)
        self.assertTrue(feedback.visible(1.1))
        feedback.config["enabled"] = False
        self.assertFalse(feedback.visible(1.1))

    def test_old_configs_default_off_and_invalid_limits_are_repaired(self):
        old, warnings = app.validate_config({})
        self.assertFalse(old["delta_feedback"]["enabled"])
        self.assertFalse(warnings)
        for invalid in (0, -1, math.nan, math.inf, "bad"):
            loaded, warnings = app.validate_config({"delta_feedback": {"x_px": invalid}})
            self.assertEqual(loaded["delta_feedback"]["x_px"], DEFAULT_DELTA["x_px"])
            self.assertTrue(warnings)

    def test_preview_uses_one_uniform_scale_for_actual_source_pixels(self):
        left, top, scale = preview_transform(440, 320, 486, 274)
        self.assertAlmostEqual((440 - 2 * left) / (320 - 2 * top), 486 / 274)
        self.assertAlmostEqual(((left + 10 * scale) - left) / scale, 10)

    def test_preview_resolution_defaults_and_legacy_custom_size_survive_validation(self):
        defaults, _ = app.validate_config({})
        self.assertEqual(defaults["delta_feedback"]["preview_source"], "preset")
        self.assertEqual(defaults["delta_feedback"]["preview_width"] / defaults["delta_feedback"]["preview_height"], 16 / 9)
        for source in (None, "custom", "obs"):
            config = {"preview_width": 321, "preview_height": 201}
            if source:
                config["preview_source"] = source
            checked, warnings = app.validate_config({"delta_feedback": config})
            self.assertFalse(warnings)
            self.assertEqual(checked["delta_feedback"]["preview_source"], source or "custom")
            self.assertEqual(checked["delta_feedback"]["preview_width"], 321)
            self.assertEqual(checked["delta_feedback"]["preview_height"], 201)

    def test_recorded_delta_feedback_is_independent_of_circle_grading(self):
        config = deepcopy(app.DEFAULT_CONFIG)
        config["delta_feedback"] = self.config
        recorder = app.SessionRecorder(config, "manual")
        tracker = app.PointTracker()
        tracker.update((10, 10), 0)
        tracker.update(None, 1)
        tracker.update((30, 5), 2)
        over = delta_exceeded(tracker.delta, self.config)
        recorder.add_frame(None, tracker.last_point, (0, 0, 486, 274), True, tracker, False, over)
        result = recorder.finish()
        self.assertEqual(result["grade"], "N/A")
        self.assertEqual(result["beep_count"], 1)
        self.assertEqual(recorder.data[0][-1], True)
        self.assertAlmostEqual(recorder.data[0][13], math.hypot(20, -5))



if __name__ == "__main__":
    unittest.main()
