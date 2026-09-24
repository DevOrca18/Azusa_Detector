import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main as app


class PreviewSelectionTests(unittest.TestCase):
    def view(self):
        return SimpleNamespace(monitor_running=False, monitor_pending=False, closing=False,
                               obs_window_var=Mock(get=Mock(return_value="OBS test")),
                               last_source_available=None, live_preview=SimpleNamespace(active=True),
                               refresh_windows=Mock(), update_connection_status=Mock())

    def test_missing_source_keeps_live_panel_polling_to_clear_stale_frames(self):
        view = self.view()
        with patch.object(app.win32gui, "FindWindow", return_value=0):
            app.App.check_preview_source(view)
        self.assertTrue(view.live_preview.active)
        self.assertFalse(view.last_source_available)
        with patch.object(app.win32gui, "FindWindow", return_value=123), patch.object(app.win32gui, "IsIconic", return_value=False):
            app.App.check_preview_source(view)
        self.assertTrue(view.last_source_available)
        self.assertTrue(view.live_preview.active)

    def test_minimized_source_keeps_live_panel_and_running_mode_keeps_source(self):
        view = self.view()
        view.last_source_available = True
        with patch.object(app.win32gui, "FindWindow", return_value=123), patch.object(app.win32gui, "IsIconic", return_value=True):
            app.App.check_preview_source(view)
        self.assertFalse(view.last_source_available)
        self.assertTrue(view.live_preview.active)
        view.monitor_running = True
        view.refresh_windows.reset_mock()
        app.App.check_preview_source(view)
        view.refresh_windows.assert_not_called()

    def test_window_discovery_retries_when_obs_opens_later(self):
        view = self.view()
        with patch.object(app.win32gui, "FindWindow", side_effect=(0, 123)), patch.object(app.win32gui, "IsIconic", return_value=False):
            app.App.check_preview_source(view)
        view.refresh_windows.assert_called_once_with(update_status=False)
        self.assertTrue(view.last_source_available)


if __name__ == "__main__":
    unittest.main()
