import unittest
from copy import deepcopy
from string import Formatter
from unittest.mock import patch

import main as app
import localization
from monitor_engine import MonitorEngine


class MonitorEngineTests(unittest.TestCase):
    def setUp(self):
        self.config = deepcopy(app.DEFAULT_CONFIG)
        self.config["auto"]["enabled"] = False
        self.config["delta_feedback"].update({"enabled": True, "x_px": 10.0, "y_px": 10.0})
        self.rect = (20, 30, 200, 160)
        self.rect_patch = patch.object(app, "detect_black_rectangle", side_effect=lambda frame: (self.rect, frame))
        self.rect_patch.start()
        self.addCleanup(self.rect_patch.stop)
        self.engine = MonitorEngine(app, self.config)

    def frame(self, point=None):
        frame = app.np.full((240, 300, 3), 70, dtype=app.np.uint8)
        frame[30:190, 20:220] = 0
        if point is not None:
            app.cv2.circle(frame, point, 3, (255, 255, 255), -1)
        return frame

    def test_preview_crops_only_detection_region_and_has_no_side_effects(self):
        with patch.object(app, "play_alert_sound", return_value=True) as sound, patch.object(app, "SessionRecorder") as record, patch.object(app, "draw_hud") as hud:
            first = self.engine.step(self.frame((100, 100)), None, 1)
            self.engine.step(self.frame((150, 100)), None, 2)
        self.assertEqual(first.shape, (160, 200, 3))
        self.assertTrue((first[0, 0] == 0).all())
        self.assertTrue(self.engine.feedback.over_threshold)
        sound.assert_not_called()
        record.assert_not_called()
        hud.assert_not_called()

    def test_large_reappearance_compares_with_last_valid_and_warns(self):
        self.engine.start(self.config)
        self.engine.record()
        with patch.object(app, "play_alert_sound", return_value=True) as sound:
            self.engine.step(self.frame((100, 100)), None, 1)
            self.engine.step(self.frame(), None, 2)
            self.engine.missing(3)
            self.engine.step(self.frame((130, 80)), None, 4)
        self.assertEqual(self.engine.tracker.delta, (30, -20))
        self.assertEqual(self.engine.tracker.delta_seconds, 3)
        self.assertTrue(self.engine.feedback.over_threshold)
        sound.assert_called_once()
        self.assertEqual(self.engine.session.data[-1][10:13], [30, -20, 3])
        self.assertEqual([row[-1] for row in self.engine.session.data], [None, None, None, True])

    def test_small_reappearance_is_safe_because_delta_is_small(self):
        self.engine.start(self.config)
        with patch.object(app, "play_alert_sound", return_value=True) as sound:
            for now, point in enumerate(((100, 100), None, (102, 103))):
                self.engine.step(self.frame(point), None, now)
        self.assertEqual(self.engine.tracker.delta, (2, 3))
        self.assertFalse(self.engine.feedback.over_threshold)
        sound.assert_not_called()

    def test_live_threshold_edit_keeps_reference_and_logs_new_limits(self):
        self.engine.start(self.config)
        self.engine.record()
        self.engine.step(self.frame((100, 100)), None, 1)
        changed = deepcopy(self.config)
        changed["delta_feedback"]["x_px"] = 2
        self.engine.configure(changed)
        with patch.object(app, "play_alert_sound", return_value=True) as sound:
            self.engine.step(self.frame((104, 100)), None, 2)
        self.assertEqual(self.engine.tracker.delta, (4, 0))
        self.assertEqual(self.engine.session.data[-1][16], 2)
        sound.assert_called_once()

    def test_toggle_off_suppresses_beep_and_mute_preserves_alert_metrics(self):
        self.engine.start(self.config)
        self.engine.muted = True
        with patch.object(app, "play_alert_sound", return_value=True) as sound:
            self.engine.step(self.frame((100, 100)), None, 1)
            self.engine.step(self.frame((130, 100)), None, 2)
            self.assertEqual(sound.call_args.args, (True,))
            self.assertTrue(self.engine.feedback.over_threshold)
            changed = deepcopy(self.config)
            changed["delta_feedback"]["enabled"] = False
            self.engine.configure(changed)
            self.engine.step(self.frame((160, 100)), None, 4)
            self.assertEqual(sound.call_count, 1)
        self.assertIsNone(self.engine.feedback.over_threshold)

    def test_circle_uses_circle_sound_without_delta_alert(self):
        self.config["detect"]["circle_enabled"] = True
        self.engine.start(self.config)
        with patch.object(app, "play_alert_sound", return_value=True) as sound:
            self.engine.step(self.frame((120, 110)), None, 1)
            self.engine.step(self.frame((150, 110)), None, 2)
            sound.assert_not_called()
            self.engine.step(self.frame((180, 110)), None, 3)
            sound.assert_called_once()
        self.assertIsNone(self.engine.feedback.over_threshold)

    def test_stop_saves_once_and_preview_remains_silent(self):
        self.engine.start(self.config)
        self.engine.record()
        self.engine.step(self.frame((100, 100)), None, 1)
        with patch.object(app, "finish_recording", side_effect=lambda session, _: session.finish()) as save, patch.object(app, "play_alert_sound", return_value=True) as sound:
            self.engine.stop()
            self.engine.stop()
            self.engine.step(self.frame((150, 100)), None, 3)
        save.assert_called_once()
        sound.assert_not_called()
        self.assertFalse(self.engine.running)
        self.assertIsNone(self.engine.session)
        self.assertEqual(self.engine.last_result["grade"], "N/A")

    def test_failed_save_retains_session_for_retry(self):
        self.engine.start(self.config)
        self.engine.record()
        self.engine.step(self.frame((100, 100)), None, 1)
        with patch.object(app, "finish_recording", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.engine.stop()
        self.assertIsNotNone(self.engine.session)
        self.assertTrue(self.engine.running)

    def test_auto_recording_and_timer_loss_follow_same_live_pipeline(self):
        self.config["auto"]["enabled"] = True
        self.config["auto"]["debounce_frames"] = 1
        self.config["auto"]["end_mode"] = "timer"
        self.engine.start(self.config)
        with patch.object(self.engine.timer, "read_seconds", return_value=(58, None, "template")), patch("monitor_engine.time.time", return_value=10):
            self.engine.step(self.frame((100, 100)), self.frame(), 1)
        self.assertEqual(self.engine.session.source, "auto")
        with patch("monitor_engine.time.time", return_value=20), patch.object(app, "finish_recording", side_effect=lambda session, _: session.finish()) as save:
            self.engine.missing(4)
        save.assert_called_once()
        self.assertIsNone(self.engine.session)

    def test_fixed_duration_survives_missing_captures_and_saves_at_deadline(self):
        self.config["auto"].update({"enabled": True, "debounce_frames": 1})
        self.engine.start(self.config)
        with patch.object(self.engine.timer, "read_seconds", return_value=(58, None, "template")):
            self.engine.step(self.frame((100, 100)), self.frame(), 10)
        session = self.engine.session
        with patch.object(app, "finish_recording", side_effect=lambda recorder, _: recorder.finish()) as save:
            # Wall-clock changes and missing game/OBS frames do not end the run.
            with patch("monitor_engine.time.time", return_value=10_000):
                self.engine.missing(20)
                self.engine.step(self.frame((105, 100)), None, 35)
            self.engine.missing(69.999)
            self.assertIs(self.engine.session, session)
            save.assert_not_called()
            self.assertEqual(session.data[1][2:4], [None, None])
            with patch("monitor_engine.time.monotonic", return_value=40):
                state = self.engine.snapshot()
            self.assertEqual(state["remaining"], 30)
            self.assertEqual(state["elapsed"], 30)
            self.engine.missing(70)
            self.engine.missing(71)
        save.assert_called_once()
        self.assertIsNone(self.engine.session)
        self.assertTrue(self.engine.running)
        self.assertEqual(len(session.data), 4)

    def test_duration_deadline_saves_before_processing_a_late_frame(self):
        self.config["auto"].update({"enabled": True, "debounce_frames": 1, "duration_sec": 5})
        self.engine.start(self.config)
        with patch.object(self.engine.timer, "read_seconds", return_value=(58, None, "template")):
            self.engine.step(self.frame((100, 100)), self.frame(), 10)
        session = self.engine.session
        with patch.object(app, "finish_recording", side_effect=lambda recorder, _: recorder.finish()) as save:
            self.engine.step(self.frame((105, 100)), None, 15)
        save.assert_called_once()
        self.assertEqual(len(session.data), 1)
        self.assertIsNone(self.engine.session)

    def test_duration_deadline_does_not_stop_manual_recordings(self):
        self.config["auto"]["enabled"] = True
        self.engine.start(self.config)
        self.engine.record()
        with patch.object(app, "finish_recording") as save:
            self.engine.check_deadline(1_000_000)
        save.assert_not_called()
        self.assertEqual(self.engine.session.source, "manual")

    def test_failed_deadline_save_can_retry_without_losing_the_recording(self):
        self.config["auto"].update({"enabled": True, "debounce_frames": 1})
        self.engine.start(self.config)
        with patch.object(self.engine.timer, "read_seconds", return_value=(58, None, "template")):
            self.engine.step(self.frame((100, 100)), self.frame(), 10)
        with patch.object(app, "finish_recording", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.engine.check_deadline(70)
        self.assertIsNotNone(self.engine.session)
        self.assertEqual(self.engine.auto.deadline, 70)
        with patch.object(app, "finish_recording", side_effect=lambda recorder, _: recorder.finish()) as save:
            self.engine.check_deadline(71)
        save.assert_called_once()
        self.assertIsNone(self.engine.session)

    def test_all_translation_placeholders_match_in_every_language(self):
        for row in localization.ROWS + localization.OVERLAYS:
            fields = [{field for _, field, _, _ in Formatter().parse(text) if field} for text in row]
            self.assertTrue(all(value == fields[0] for value in fields), row[0])
        for code in localization.LANGUAGES:
            localization.set_language(code)
            self.assertEqual(localization.get_language(), code)
            self.assertNotIn("요", localization.t("필수 설정: {items}", items="X"))
        localization.set_language("ko")


if __name__ == "__main__":
    unittest.main()
