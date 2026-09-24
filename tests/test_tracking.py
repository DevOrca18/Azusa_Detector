import csv
import tempfile
import unittest
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import main as app


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.config = deepcopy(app.DEFAULT_CONFIG)
        self.rect = (20, 30, 200, 160)

    def frame(self, *points):
        frame = np.zeros((240, 300, 3), dtype=np.uint8)
        for point in points:
            cv2.circle(frame, point, 3, (255, 255, 255), -1)
        return frame

    def test_missing_frames_compare_next_detection_to_last_valid_point(self):
        tracker = app.PointTracker()
        tracker.update(None, 0.0)
        self.assertIsNone(tracker.origin)
        tracker.update((100.0, 100.0), 1.0)
        self.assertEqual(tracker.relative, (0.0, 0.0))
        self.assertIsNone(tracker.delta)
        tracker.update((110.0, 105.0), 2.0)
        tracker.update(None, 3.0)
        tracker.update(None, 4.0)
        self.assertFalse(tracker.detected)
        self.assertEqual(tracker.last_point, (110.0, 105.0))
        self.assertEqual(tracker.delta, (10.0, 5.0))
        tracker.update((107.0, 112.0), 5.0)
        self.assertEqual(tracker.relative, (7.0, 12.0))
        self.assertEqual(tracker.delta, (-3.0, 7.0))
        self.assertEqual(tracker.delta_seconds, 3.0)

    def test_zero_coordinate_is_a_valid_reference(self):
        tracker = app.PointTracker()
        tracker.update((0.0, 0.0), 0.0)
        tracker.update(None, 1.0)
        tracker.update((2.0, 3.0), 2.0)
        self.assertEqual(tracker.delta, (2.0, 3.0))

    def test_windowless_build_does_not_hide_another_app(self):
        with patch.object(app.windll.kernel32, "GetConsoleWindow", return_value=0), \
                patch.object(app.win32gui, "ShowWindow") as show:
            app.hide_console()
        show.assert_not_called()

    def test_detects_centers_inside_and_outside_independent_of_circle(self):
        for point, outside in [((120, 110), False), ((165, 110), False), ((170, 110), True)]:
            with self.subTest(point=point):
                detected = app.detect_white_point(self.frame(point), self.rect)
                self.assertEqual(detected, point)
                self.assertEqual(app.judge_circle(detected, self.rect, 45, True), outside)
                self.assertIsNone(app.judge_circle(detected, self.rect, 45, False))

    def test_rejects_missing_noise_large_blocks_and_ambiguous_points(self):
        noise = self.frame()
        noise[70, 50] = 255
        large = self.frame()
        large[50:150, 50:150] = 255
        for frame in (self.frame(), noise, large, self.frame((70, 70), (150, 150))):
            self.assertIsNone(app.detect_white_point(frame, self.rect))
        self.assertIsNone(app.judge_circle(None, self.rect, 45, True))

    def test_small_speck_does_not_move_target_center(self):
        frame = self.frame((120, 110))
        frame[50, 50] = 255
        self.assertEqual(app.detect_white_point(frame, self.rect), (120, 110))

    def test_recorder_excludes_unjudged_frames_without_losing_coordinates(self):
        recorder = app.SessionRecorder(self.config, "manual")
        tracker = app.PointTracker()
        samples = [((120, 110), True), ((180, 110), False), (None, True), ((190, 110), True)]
        for now, (point, enabled) in enumerate(samples):
            tracker.update(point, float(now))
            outside = app.judge_circle(point, self.rect, 45, enabled)
            recorder.add_frame(outside, point, self.rect, outside is True, tracker, enabled)
        result = recorder.finish()
        self.assertEqual((result["total_frames"], result["detected_frames"], result["graded_frames"]), (4, 3, 2))
        self.assertEqual(result["outside_ratio"], 0.5)
        self.assertEqual(tracker.relative, (70, 0))
        self.assertEqual(tracker.delta, (10, 0))
        self.assertEqual(tracker.delta_seconds, 2.0)
        self.assertEqual(recorder.data[1][8:12], [60, 0, 60, 0])
        self.assertEqual(recorder.data[2][2:4], [None, None])
        self.assertEqual(recorder.data[2][8:13], [None] * 5)

    def test_unjudged_session_has_no_grade_and_can_be_rendered_and_saved(self):
        recorder = app.SessionRecorder(self.config, "manual")
        tracker = app.PointTracker()
        tracker.update((120, 110), 0.0)
        recorder.add_frame(None, tracker.last_point, self.rect, False, tracker, False)
        result = recorder.finish()
        self.assertEqual(result["grade"], "N/A")
        self.assertIsNone(result["outside_ratio"])
        frame = np.zeros((820, 1280, 3), dtype=np.uint8)
        app.draw_hud(frame, 45, None, False, "AUTO: OFF", None, None, "", result, False, tracker)
        app.draw_result_card(frame, result)
        with tempfile.TemporaryDirectory() as folder, patch.object(app, "record_folder", return_value=folder):
            app.append_session_summary(result)
            filename = app.save_record_data(recorder.data, self.rect)
            with open(Path(folder) / "sessions_v2.csv", newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(rows[0]["graded_frames"], "0")
            self.assertEqual(rows[0]["outside_ratio"], "")
            with open(filename, newline="", encoding="utf-8") as file:
                rows = list(csv.reader(file))
            self.assertEqual(len(rows[1]), len(rows[2]))
            self.assertEqual(rows[2][10:13], ["", "", ""])

    def test_missing_interval_does_not_inflate_outside_duration(self):
        start = datetime(2026, 1, 1)
        with patch.object(app, "datetime") as clock:
            clock.now.return_value = start
            recorder = app.SessionRecorder(self.config, "manual")
            tracker = app.PointTracker()
            for seconds, point in [(0, (190, 110)), (1, (190, 110)), (20, None), (30, (190, 110))]:
                clock.now.return_value = start + timedelta(seconds=seconds)
                tracker.update(point, seconds)
                recorder.add_frame(app.judge_circle(point, self.rect, 45, True), point, self.rect, False, tracker, True)
            result = recorder.finish()
        self.assertEqual(result["max_outside_s"], 1.0)

    def test_old_config_defaults_to_position_and_off_round_trips(self):
        config, warnings = app.validate_config({"detect": {"circle_radius": 10}})
        self.assertFalse(config["detect"]["circle_enabled"])
        self.assertFalse(warnings)
        config["detect"]["circle_enabled"] = False
        with tempfile.TemporaryDirectory() as folder, patch.object(app, "CONFIG_FILE", str(Path(folder) / "config.json")):
            app.save_config(config)
            loaded, warnings = app.load_config()
        self.assertFalse(loaded["detect"]["circle_enabled"])
        self.assertFalse(warnings)


if __name__ == "__main__":
    unittest.main()
