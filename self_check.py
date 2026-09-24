"""Offline dependency/resource check usable from the standalone EXE."""
import json
import os
import platform
import sys
import tempfile
import traceback
import wave
import time
from pathlib import Path
from unittest.mock import patch



def run_self_check(app):
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)), "checks": {}}
    report_path = Path(app.app_base_dir()) / "self-test.json"
    original_config, original_digits, original_record_folder = app.CONFIG_FILE, app.EXTERNAL_DIGIT_DIR, app.record_folder
    root = None
    try:
        report["python"] = platform.python_version()
        report["architecture"] = platform.machine()
        report["opencv"] = app.cv2.__version__
        report["numpy"] = app.np.__version__
        with tempfile.TemporaryDirectory(prefix="Azusa-check-") as temp:
            app.CONFIG_FILE = os.path.join(temp, "config.json")
            app.EXTERNAL_DIGIT_DIR = os.path.join(temp, "assets", "digits")
            records = os.path.join(temp, "azusa_record")
            os.makedirs(records)
            app.record_folder = lambda: records
            config, warnings = app.load_config()
            config["detect"]["circle_enabled"] = False
            app.save_config(config)
            loaded, _ = app.load_config()
            if loaded["detect"]["circle_enabled"]:
                raise RuntimeError("Config round trip failed")
            report["checks"]["config_save_load"] = True

            with wave.open(app.SOUND_FILE, "rb") as sound:
                if sound.getnframes() <= 0:
                    raise RuntimeError("Alert sound is empty")
            report["checks"]["bundled_alert_sound"] = True
            detector = app.TimerDetector(config)
            if len(detector.templates) != 10:
                raise RuntimeError(f"Expected 10 bundled digit templates, got {len(detector.templates)}")
            report["checks"]["bundled_digits"] = 10

            frame = app.np.zeros((160, 200, 3), dtype=app.np.uint8)
            app.cv2.circle(frame, (100, 80), 4, (255, 255, 255), -1)
            point = app.detect_white_point(frame, (0, 0, 200, 160))
            if point != (100.0, 80.0):
                raise RuntimeError("Synthetic point detection failed")
            tracker = app.PointTracker()
            tracker.update(point, 1.0)
            tracker.update(None, 2.0)
            tracker.update((115.0, 73.0), 3.0)
            if tracker.delta != (15.0, -7.0) or tracker.delta_seconds != 2.0:
                raise RuntimeError("Tracking across missed frames failed")
            recorder = app.SessionRecorder(config, "manual")
            recorder.add_frame(None, tracker.last_point, (0, 0, 200, 160), False, tracker, False)
            result = app.finish_recording(recorder, (0, 0, 200, 160))
            if result["grade"] != "N/A":
                raise RuntimeError("Disabled-circle grading failed")
            report["checks"]["tracking_and_csv"] = True

            root = app.App(config, warnings)
            root.title("Azusa Detector - self-test")
            callback_errors = []
            root.report_callback_exception = lambda *args: callback_errors.append(str(args))
            root.update()
            if root.brand_rail.art is None or root.brand_rail.photo is None:
                raise RuntimeError("Character sidebar artwork was not bundled or rendered")
            report["checks"]["bundled_character_artwork"] = True
            root.update()
            if root.monitor_mode_var.get() != "position" or not all(control.instate(["disabled"]) for control in root.circle_controls):
                raise RuntimeError("Position-only setup mode was not restored")
            if root.detect_section.winfo_manager() or root.grading_section.winfo_manager() or not root.live_preview.winfo_manager():
                raise RuntimeError("Position setup did not show only its relevant sections")
            root.monitor_mode_var.set("circle")
            root.update_mode_controls()
            if any(control.instate(["disabled"]) for control in root.circle_controls):
                raise RuntimeError("Circle setup controls are still disabled")
            if root.delta_settings.controls.winfo_manager() or not root.live_preview.winfo_manager() or not root.grading_section.winfo_manager():
                raise RuntimeError("Circle setup did not show only its relevant sections")
            root.radius_var.set("45")
            root.circle_beep_var.set(False)
            if root.read_settings()["detect"]["circle_beep_enabled"]:
                raise RuntimeError("Circle sound toggle did not reach config")
            root.monitor_mode_var.set("position")
            root.update_mode_controls()
            root.delta_settings.guide_enabled.set(True)
            if not root.read_settings()["delta_feedback"]["guide_enabled"]:
                raise RuntimeError("Live guide toggle did not reach config")
            report["checks"]["mode_specific_sound_and_guide_settings"] = True
            # Exercise bundled Tcl/Tk, ttkthemes, pygetwindow, GDI and PrintWindow.
            titles = app.gw.getAllTitles()
            if root.title() not in titles:
                raise RuntimeError("Native window enumeration failed")
            hwnd = app.win32gui.FindWindow(None, root.title())
            captured = app.capture_window(hwnd)
            if captured.size == 0:
                raise RuntimeError("Window capture failed")
            report["checks"]["tk_theme_and_win32_capture"] = True
            root.monitor_mode_var.set("position")
            root.update_mode_controls()
            root.delta_settings.enabled.set(True)
            root.delta_settings.x_px.set("10")
            # UI localization rebuilds must preserve values and remove stale traces.
            from localization import LANGUAGES
            for code in ("en", "ja", "zh", "ko"):
                root.language_var.set(LANGUAGES[code])
                root.change_language()
                root.update()
                if not root.delta_settings.guide_enabled.get() or root.circle_beep_var.get() or root.radius_var.get() != "45":
                    raise RuntimeError("Language switching discarded edits")
            report["checks"]["four_language_switching"] = True
            root.delta_settings.method.set("distance")
            root.update()
            if root.delta_settings.axes_fields.winfo_manager() or not root.delta_settings.distance_fields.winfo_manager():
                raise RuntimeError("Inactive X/Y fields are visible")
            root.delta_settings.x_px.set("invalid")
            root.read_settings()  # Hidden X is not a required distance field.
            root.delta_settings.method.set("axes")
            root.delta_settings.x_px.set("10")
            report["checks"]["conditional_threshold_inputs"] = True
            root.geometry("1320x860")
            root.update()
            if root.left_scroller.scrollbar.winfo_manager():
                raise RuntimeError("Unnecessary scrollbar at full default size")
            root.toggle_settings()
            root.update()
            if root.left_scroller.winfo_manager():
                raise RuntimeError("Settings did not collapse")
            root.toggle_settings()
            root.update()
            if not root.left_scroller.winfo_manager():
                raise RuntimeError("Settings did not expand")
            report["checks"]["collapsible_settings_and_scrollbar"] = True
            if hasattr(root, "preview_tabs") or not root.live_preview.winfo_manager():
                raise RuntimeError("Expected one integrated live panel without sample tabs")
            if set(root.live_preview.actions) != {"record", "mute", "calibrate", "stop", "reset", "refresh", "sample"}:
                raise RuntimeError("Shortcut action buttons are missing")
            if root.input_error_label.winfo_manager():
                raise RuntimeError("Empty error area is still visible")
            sections = [root.window_section, root.mode_section, root.delta_settings.controls, root.record_section]
            gaps = [second.winfo_y() - first.winfo_y() - first.winfo_height() for first, second in zip(sections, sections[1:])]
            if len(set(gaps)) != 1:
                raise RuntimeError("Settings card gaps differ: " + str(gaps))
            report["checks"]["single_live_panel_shortcut_buttons_consistent_cards"] = True
            from ui_theme import USER_GUIDE_URL
            with patch("ui_theme.webbrowser.open_new_tab") as browser:
                root.brand_rail.repository_button.invoke()
                browser.assert_called_once_with(USER_GUIDE_URL)
            with patch.object(app.os, "startfile") as folder:
                root.brand_rail.records_button.invoke()
                folder.assert_called_once_with(records)
            report["checks"]["repository_and_recording_buttons"] = True
            root.obs_window_var.set(root.title())
            root.game_window_var.set("")
            if not root.start_button.instate(["disabled"]):
                raise RuntimeError("Start should be unavailable without a selected game window")
            if not root.required_labels["game"].cget("text"):
                raise RuntimeError("Missing required window is not marked")
            disabled_background = root.style.lookup("Primary.TButton", "background", ("disabled",))
            if disabled_background == root.style.lookup("Primary.TButton", "background"):
                raise RuntimeError("Disabled start button kept its active background")
            report["checks"]["required_fields_and_disabled_button"] = True
            root.game_window_var.set(root.title())
            root.geometry("1160x740")
            root.update()
            if root.start_button.winfo_rooty() + root.start_button.winfo_height() > root.winfo_rooty() + root.winfo_height():
                raise RuntimeError("Start button is clipped at the supported compact size")
            root.delta_settings.x_px.set("invalid")
            with patch.object(app.messagebox, "showwarning") as warning:
                root.start_monitoring()
                if not warning.called or hasattr(root, "monitor_target"):
                    raise RuntimeError("Invalid input unexpectedly started monitoring")
            root.delta_settings.x_px.set("10")
            root.obs_window_var.set("Azusa self-check nonexistent window")
            with patch.object(app.messagebox, "showwarning") as warning:
                root.start_monitoring()
                if not warning.called or hasattr(root, "monitor_target"):
                    raise RuntimeError("Closed window unexpectedly started monitoring")
            root.obs_window_var.set(root.title())
            report["checks"]["setup_input_guards_and_compact_layout"] = True
            from live_preview import CaptureWorker
            capture_patch = patch.object(CaptureWorker, "capture", return_value=frame)
            capture_patch.start()
            root.start_monitoring()
            if root.monitor_target[2]["detect"]["circle_enabled"]:
                raise RuntimeError("Start Monitoring did not use the selected mode")
            if not root.monitor_target[2]["delta_feedback"]["enabled"]:
                raise RuntimeError("Start Monitoring did not save delta feedback settings")
            if not root.monitor_target[2]["delta_feedback"]["guide_enabled"]:
                raise RuntimeError("Start Monitoring did not save guide selection")
            deadline = time.monotonic() + 4
            while not root.monitor_running and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            if not root.monitor_running or not root.winfo_exists():
                raise RuntimeError("Embedded monitoring did not start in the setup window")
            if not root.obs_window_combo.instate(["disabled"]):
                raise RuntimeError("Source selection is not locked while monitoring")
            root.start_monitoring()
            deadline = time.monotonic() + 4
            while root.monitor_running and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            if root.monitor_running or not root.winfo_exists():
                raise RuntimeError("Stop did not return to preview in the same window")
            report["checks"]["embedded_preview_live_preview_lifecycle"] = True
            capture_patch.stop()
            if callback_errors:
                raise RuntimeError("Tk callbacks failed: " + repr(callback_errors))
            root.close_app()
            deadline = time.monotonic() + 4
            worker = root.live_preview.worker
            while worker.thread.is_alive() and time.monotonic() < deadline:
                root.update()
                time.sleep(0.02)
            if worker.thread.is_alive():
                raise RuntimeError("Capture worker did not stop")
            root.update()
            root = None
            report["checks"]["startup_mode_selection"] = True

        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if root is not None:
            root.destroy()
        app.CONFIG_FILE, app.EXTERNAL_DIGIT_DIR, app.record_folder = original_config, original_digits, original_record_folder
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if report["ok"] else 1
