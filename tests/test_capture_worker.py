import os
import unittest
from unittest.mock import Mock, patch

import main as app
from live_preview import CaptureWorker


class CaptureWorkerTests(unittest.TestCase):
    def worker(self):
        with patch("live_preview.threading.Thread"):
            return CaptureWorker(app, app.DEFAULT_CONFIG)

    def test_capture_rejects_own_ui_to_prevent_recursive_print_deadlock(self):
        worker = self.worker()
        with patch.object(app.win32gui, "FindWindow", return_value=123), \
                patch.object(app.win32gui, "IsIconic", return_value=False), \
                patch("live_preview.win32process.GetWindowThreadProcessId", return_value=(1, os.getpid())), \
                patch.object(app, "capture_window") as capture:
            with self.assertRaises(ValueError):
                worker.capture("self")
        capture.assert_not_called()

    def test_gdi_bgra_preserves_red_and_blue_channels(self):
        worker = self.worker()
        pixels = app.np.array([[[5, 20, 200, 255]]], dtype=app.np.uint8)
        with patch.object(app.win32gui, "FindWindow", return_value=123), \
                patch.object(app.win32gui, "IsIconic", return_value=False), \
                patch("live_preview.win32process.GetWindowThreadProcessId", return_value=(1, -1)), \
                patch.object(app, "capture_window", return_value=pixels):
            frame = worker.capture("test")
        self.assertEqual(frame.tolist(), [[[5, 20, 200]]])

    def test_optional_game_capture_failure_does_not_drop_obs_tracking(self):
        worker = self.worker()
        with patch.object(app.win32gui, "FindWindow", return_value=123), \
                patch.object(app.win32gui, "IsIconic", return_value=False), \
                patch("live_preview.win32process.GetWindowThreadProcessId", return_value=(1, -1)), \
                patch.object(app, "capture_window", side_effect=OSError("game closed")):
            self.assertIsNone(worker.capture("game", required=False))
            with self.assertRaises(OSError):
                worker.capture("obs", required=True)

    def test_capture_error_after_record_command_is_not_a_save_error(self):
        worker = self.worker()
        engine = Mock(running=False)
        engine.snapshot.return_value = {"running": False}
        worker.send("record")

        def failed_capture(*args):
            worker.send("close")
            raise ValueError("source disappeared")

        with patch("live_preview.MonitorEngine", return_value=engine), patch.object(worker, "capture", side_effect=failed_capture):
            worker.run()
        events = []
        while not worker.events.empty():
            events.append(worker.events.get_nowait()[0])
        self.assertEqual(events, ["closed"])
        self.assertEqual(worker.results.get_nowait()[2], "source disappeared")

    def test_failed_native_capture_releases_gdi_resources(self):
        dc, bitmap = Mock(), Mock()
        saved_dc = dc.CreateCompatibleDC.return_value
        with patch.object(app.win32gui, "GetClientRect", return_value=(0, 0, 100, 100)), \
                patch.object(app.win32gui, "GetWindowDC", return_value=9), \
                patch.object(app.win32ui, "CreateDCFromHandle", return_value=dc), \
                patch.object(app.win32ui, "CreateBitmap", return_value=bitmap), \
                patch.object(app.windll.user32, "PrintWindow", return_value=0), \
                patch.object(app.win32gui, "DeleteObject") as delete, \
                patch.object(app.win32gui, "ReleaseDC") as release:
            with self.assertRaises(ValueError):
                app.capture_window(123)
        delete.assert_called_once_with(bitmap.GetHandle.return_value)
        saved_dc.DeleteDC.assert_called_once()
        dc.DeleteDC.assert_called_once()
        release.assert_called_once_with(123, 9)


if __name__ == "__main__":
    unittest.main()
