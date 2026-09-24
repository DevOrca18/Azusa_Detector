import csv
import json
import math
import os
import sys
import time
import winsound
import tkinter as tk
from copy import deepcopy
from ctypes import windll
from datetime import datetime
from tkinter import messagebox, ttk

import cv2
import numpy as np
import pygetwindow as gw
import ttkthemes
import win32con
import win32gui
import win32ui

from delta_feedback import DEFAULT_DELTA, PREVIEW_PRESETS, DeltaFeedback, threshold_label
from setup_view import build_setup
from ui_theme import bgr, configure_theme
from localization import LANGUAGES, get_language, set_language, t, overlay_text
import unicode_text
from activity_log import ActivityLog


WHITE_THRESHOLD_LOW = np.array([0, 0, 200])
WHITE_THRESHOLD_HIGH = np.array([180, 25, 255])

DEFAULT_CONFIG = {
    "language": "ko",
    "windows": {"obs_title": "", "game_title": ""},
    "grading": {"good_max": 0.05, "soso_max": 0.15},
    "auto": {
        "enabled": True,
        "start_band": [55, 59],
        "end_band": [0, 1],
        "end_mode": "duration",
        "duration_sec": 60,
        "debounce_frames": 3,
        "grace_sec": 2.0,
        "cooldown_sec": 5.0,
        "ocr_fallback": False,
    },
    "timer_roi": {"x_ratio": 0.42, "y_ratio": -0.98, "w_ratio": 0.13, "h_ratio": 0.08},
    "detect": {"circle_radius": 45, "circle_enabled": False, "circle_beep_enabled": True},
    "delta_feedback": DEFAULT_DELTA.copy(),
}

DIGIT_CANDIDATE_SCORE_MIN = 0.25
RESULT_OVERLAY_SEC = 3.0
STATUS_OVERLAY_SEC = 2.0
DISPLAY_WINDOW_NAME = "Display"
DISPLAY_MAX_WIDTH = 1280
DISPLAY_MAX_HEIGHT = 820

if getattr(sys, "frozen", False):
    APP_BASE_DIR = os.path.dirname(sys.executable)
else:
    APP_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def hide_console():
    try:
        console_window = windll.kernel32.GetConsoleWindow()
        if console_window:
            win32gui.ShowWindow(console_window, win32con.SW_HIDE)
    except Exception:
        pass


def app_base_dir():
    return APP_BASE_DIR


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = app_base_dir()
    return os.path.join(base_path, relative_path)


CONFIG_FILE = os.path.join(app_base_dir(), "config.json")
SOUND_FILE = resource_path("alert.wav")
EXTERNAL_DIGIT_DIR = os.path.join(app_base_dir(), "assets", "digits")


def deep_merge(defaults, loaded):
    result = deepcopy(defaults)
    if not isinstance(loaded, dict):
        return result

    for key, value in loaded.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def coerce_float(value, default, warnings, name):
    try:
        return float(value)
    except (TypeError, ValueError):
        warnings.append(f"{name} is invalid; using default {default}.")
        return default


def coerce_int(value, default, warnings, name, minimum=None):
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        warnings.append(f"{name} is invalid; using default {default}.")
        return default

    if minimum is not None and int_value < minimum:
        warnings.append(f"{name} is below {minimum}; using default {default}.")
        return default
    return int_value


def coerce_bool(value, default, warnings, name):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
    warnings.append(f"{name} is invalid; using default {default}.")
    return default


def validate_band(value, default, warnings, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        warnings.append(f"{name} is invalid; using default {default}.")
        return list(default)
    try:
        low = int(value[0])
        high = int(value[1])
    except (TypeError, ValueError):
        warnings.append(f"{name} is invalid; using default {default}.")
        return list(default)

    low, high = sorted((low, high))
    if low < 0 or high > 59:
        warnings.append(f"{name} must be between 0 and 59; using default {default}.")
        return list(default)
    return [low, high]


def validate_recording_duration(value, warnings):
    try:
        seconds = float(value)
        if not math.isfinite(seconds) or not seconds.is_integer() or not 1 <= seconds <= 3600:
            raise ValueError()
        return int(seconds)
    except (TypeError, ValueError, OverflowError):
        warnings.append("auto.duration_sec must be an integer from 1 to 3600; using default 60.")
        return DEFAULT_CONFIG["auto"]["duration_sec"]


def validate_timer_roi(value, warnings):
    default = DEFAULT_CONFIG["timer_roi"]
    if not isinstance(value, dict):
        warnings.append("timer_roi is invalid; using defaults.")
        return deepcopy(default)

    roi = {
        "x_ratio": coerce_float(value.get("x_ratio"), default["x_ratio"], warnings, "timer_roi.x_ratio"),
        "y_ratio": coerce_float(value.get("y_ratio"), default["y_ratio"], warnings, "timer_roi.y_ratio"),
        "w_ratio": coerce_float(value.get("w_ratio"), default["w_ratio"], warnings, "timer_roi.w_ratio"),
        "h_ratio": coerce_float(value.get("h_ratio"), default["h_ratio"], warnings, "timer_roi.h_ratio"),
    }

    if (
        not -2.0 <= roi["x_ratio"] <= 2.0
        or not -2.0 <= roi["y_ratio"] <= 2.0
        or not 0 < roi["w_ratio"] <= 2.0
        or not 0 < roi["h_ratio"] <= 2.0
    ):
        warnings.append("timer_roi ratios are out of range; using defaults.")
        return deepcopy(default)
    return roi


def validate_windows_config(value, warnings):
    default = DEFAULT_CONFIG["windows"]
    if not isinstance(value, dict):
        warnings.append("windows is invalid; using defaults.")
        return deepcopy(default)

    return {
        "obs_title": str(value.get("obs_title") or ""),
        "game_title": str(value.get("game_title") or ""),
    }


def validate_config(config):
    warnings = []
    merged = deep_merge(DEFAULT_CONFIG, config)
    if merged.get("language") not in LANGUAGES:
        merged["language"] = "ko"

    merged["windows"] = validate_windows_config(merged.get("windows"), warnings)

    grading_config = merged["grading"] if isinstance(merged.get("grading"), dict) else {}
    if not grading_config:
        warnings.append("grading is invalid; using defaults.")
    good_max = coerce_float(
        grading_config.get("good_max"),
        DEFAULT_CONFIG["grading"]["good_max"],
        warnings,
        "grading.good_max",
    )
    soso_max = coerce_float(
        grading_config.get("soso_max"),
        DEFAULT_CONFIG["grading"]["soso_max"],
        warnings,
        "grading.soso_max",
    )
    if not (0 < good_max < soso_max < 1):
        warnings.append("grading must satisfy 0 < good_max < soso_max < 1; using defaults.")
        good_max = DEFAULT_CONFIG["grading"]["good_max"]
        soso_max = DEFAULT_CONFIG["grading"]["soso_max"]
    merged["grading"] = {"good_max": good_max, "soso_max": soso_max}

    auto_default = DEFAULT_CONFIG["auto"]
    auto_config = merged["auto"] if isinstance(merged.get("auto"), dict) else {}
    end_mode = auto_config.get("end_mode", auto_default["end_mode"])
    if end_mode not in ("duration", "timer"):
        warnings.append("auto.end_mode is invalid; using duration.")
        end_mode = auto_default["end_mode"]
    merged["auto"] = {
        "enabled": coerce_bool(auto_config.get("enabled"), auto_default["enabled"], warnings, "auto.enabled"),
        "end_mode": end_mode,
        "duration_sec": validate_recording_duration(auto_config.get("duration_sec", auto_default["duration_sec"]), warnings),
        "start_band": validate_band(auto_config.get("start_band"), auto_default["start_band"], warnings, "auto.start_band"),
        "end_band": validate_band(auto_config.get("end_band"), auto_default["end_band"], warnings, "auto.end_band"),
        "debounce_frames": coerce_int(
            auto_config.get("debounce_frames"),
            auto_default["debounce_frames"],
            warnings,
            "auto.debounce_frames",
            minimum=1,
        ),
        "grace_sec": max(
            0.1,
            coerce_float(auto_config.get("grace_sec"), auto_default["grace_sec"], warnings, "auto.grace_sec"),
        ),
        "cooldown_sec": max(
            0.0,
            coerce_float(auto_config.get("cooldown_sec"), auto_default["cooldown_sec"], warnings, "auto.cooldown_sec"),
        ),
        "ocr_fallback": coerce_bool(
            auto_config.get("ocr_fallback"),
            auto_default["ocr_fallback"],
            warnings,
            "auto.ocr_fallback",
        ),
    }

    detect_default = DEFAULT_CONFIG["detect"]
    detect_config = merged["detect"] if isinstance(merged.get("detect"), dict) else {}
    merged["detect"] = {
        "circle_beep_enabled": coerce_bool(
            detect_config.get("circle_beep_enabled", True), True, warnings, "detect.circle_beep_enabled"
        ),
        "circle_radius": coerce_int(
            detect_config.get("circle_radius"),
            detect_default["circle_radius"],
            warnings,
            "detect.circle_radius",
            minimum=1,
        ),
        "circle_enabled": coerce_bool(
            detect_config.get("circle_enabled"),
            detect_default["circle_enabled"],
            warnings,
            "detect.circle_enabled",
        ),
    }

    if merged["detect"]["circle_radius"] > 1_000_000:
        warnings.append("detect.circle_radius exceeds 1000000; using default.")
        merged["detect"]["circle_radius"] = detect_default["circle_radius"]

    delta = merged.get("delta_feedback")
    delta = delta if isinstance(delta, dict) else {}
    method = delta.get("method", "axes")
    if method not in ("axes", "distance"):
        warnings.append("delta_feedback.method must be axes or distance; using axes.")
        method = "axes"
    checked_delta = {
        "enabled": coerce_bool(delta.get("enabled", False), False, warnings, "delta_feedback.enabled"),
        "guide_enabled": coerce_bool(delta.get("guide_enabled", False), False, warnings, "delta_feedback.guide_enabled"),
        "method": method,
    }
    for key in ("x_px", "y_px", "distance_px"):
        value = coerce_float(delta.get(key, DEFAULT_DELTA[key]), DEFAULT_DELTA[key], warnings, f"delta_feedback.{key}")
        if not math.isfinite(value) or not 0 < value <= 1_000_000:
            warnings.append(f"delta_feedback.{key} must be positive and finite; using {DEFAULT_DELTA[key]}.")
            value = DEFAULT_DELTA[key]
        checked_delta[key] = value
    for key in ("preview_width", "preview_height"):
        value = coerce_int(delta.get(key, DEFAULT_DELTA[key]), DEFAULT_DELTA[key], warnings, f"delta_feedback.{key}", minimum=1)
        if value > 100_000:
            warnings.append(f"delta_feedback.{key} is too large; using {DEFAULT_DELTA[key]}.")
            value = DEFAULT_DELTA[key]
        checked_delta[key] = value
    preview_source = delta.get("preview_source", "preset")
    if preview_source not in ("preset", "custom", "obs"):
        warnings.append("delta_feedback.preview_source must be preset, custom or obs; using custom.")
        preview_source = "custom"
    # Old versions stored arbitrary OBS/sample sizes without a source selector.
    # Preserve those dimensions instead of forcing them into a 16:9 preset.
    if preview_source == "preset" and (checked_delta["preview_width"], checked_delta["preview_height"]) not in PREVIEW_PRESETS.values():
        preview_source = "custom"
    checked_delta["preview_source"] = preview_source
    merged["delta_feedback"] = checked_delta
    merged["timer_roi"] = validate_timer_roi(merged.get("timer_roi"), warnings)
    return merged, warnings


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)
        file.write("\n")


def load_config():
    created = not os.path.exists(CONFIG_FILE)
    if created:
        config = deepcopy(DEFAULT_CONFIG)
        warnings = []
    else:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                loaded = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            loaded = {}
            warnings = [f"Failed to read config.json ({error}); using defaults."]
        else:
            warnings = []
        config = loaded

    config, validation_warnings = validate_config(config)
    warnings.extend(validation_warnings)

    if created or warnings:
        save_config(config)
    return config, warnings


class App(ttkthemes.ThemedTk):
    def __init__(self, config, config_warnings):
        super().__init__(theme="equilux")

        self.config_data = config
        self.config_warnings = config_warnings
        set_language(config.get("language", "ko"))
        self.language_var = tk.StringVar(value=LANGUAGES[get_language()])
        self.activity = ActivityLog()
        self._settings_cache = None
        self._settings_log_after = None
        self._logged_settings = deepcopy(config)
        self.activity.emit("프로그램 시작")
        for warning in config_warnings:
            self.activity.emit("오류: {error}", "error", error=warning)

        self.title("Azusa Detector")
        available_width = max(900, self.winfo_screenwidth() - 60)
        available_height = max(560, self.winfo_screenheight() - 90)
        self.geometry(f"{min(1320, available_width)}x{min(920, available_height)}")
        self.minsize(min(1120, available_width), min(690, available_height))
        self.resizable(True, True)

        self.configure(background="#20242b")
        self.style = ttk.Style(self)
        self.configure_styles()

        self.obs_window_var = tk.StringVar(value=config["windows"].get("obs_title", ""))
        self.game_window_var = tk.StringVar(value=config["windows"].get("game_title", ""))
        self.radius_var = tk.StringVar(value=str(config["detect"]["circle_radius"]))
        self.circle_beep_var = tk.BooleanVar(value=config["detect"].get("circle_beep_enabled", True))
        self.monitor_mode_var = tk.StringVar(value="circle" if config["detect"]["circle_enabled"] else "position")
        self.mode_hint_var = tk.StringVar()
        self.circle_controls = []
        self.good_var = tk.StringVar(value=str(config["grading"]["good_max"]))
        self.soso_var = tk.StringVar(value=str(config["grading"]["soso_max"]))
        self.auto_enabled_var = tk.BooleanVar(value=config["auto"]["enabled"])
        self.auto_end_mode_var = tk.StringVar(value=config["auto"]["end_mode"])
        self.auto_duration_var = tk.StringVar(value=str(config["auto"]["duration_sec"]))
        self.status_var = tk.StringVar()
        self.phase_var = tk.StringVar(value=t("미리보기"))
        self.monitor_running = False
        self.monitor_pending = False
        self.closing = False
        self.settings_visible = True
        self.required_errors = {}
        self.protocol("WM_DELETE_WINDOW", self.close_app)

        build_setup(self, config, resource_path, judge_circle)

    def change_language(self, event=None):
        language = next(code for code, label in LANGUAGES.items() if label == self.language_var.get())
        if language == get_language():
            return
        self.config_data["delta_feedback"] = self.delta_settings.export()
        expanded = self.settings_visible
        sample_playing = self.live_preview.sample_playing
        if self._settings_log_after is not None:
            self.after_cancel(self._settings_log_after)
            self._settings_log_after = None
        self.live_preview.dispose()
        self.delta_settings.dispose()
        for variable, token in self.connection_traces:
            variable.trace_remove("write", token)
        for child in self.winfo_children():
            child.destroy()
        self.circle_controls = []
        self.config_data["language"] = language
        set_language(language)
        self._settings_cache = None
        self.phase_var.set(t("미리보기"))
        self.configure_styles()
        saved, _ = load_config()
        saved["language"] = language
        save_config(saved)
        build_setup(self, self.config_data, resource_path, judge_circle)
        self.activity.emit("설정 · {name}: {value}", name="Language", value=LANGUAGES[language])
        if sample_playing:
            self.live_preview.invoke_action("sample")
        if not expanded:
            self.toggle_settings()

    def destroy(self):
        if self._settings_log_after is not None:
            self.after_cancel(self._settings_log_after)
            self._settings_log_after = None
        if hasattr(self, "live_preview"):
            self.live_preview.dispose()
        if hasattr(self, "delta_settings"):
            self.delta_settings.dispose()
        super().destroy()

    def report_callback_exception(self, exc, value, traceback):
        if hasattr(self, "activity"):
            self.activity.emit("오류: {error}", "error", error=f"{exc.__name__}: {value}")
            if hasattr(self, "brand_rail") and not self.closing:
                self.brand_rail.log_view.append(self.activity.drain())
        super().report_callback_exception(exc, value, traceback)

    def update_mode_controls(self):
        circle_enabled = self.monitor_mode_var.get() == "circle"
        for control in self.circle_controls:
            control.state(["!disabled"] if circle_enabled else ["disabled"])
        self.mode_hint_var.set(
            t("고정된 원 기준 이탈 감지 · 채점")
            if circle_enabled else t("마지막 정상 감지 좌표와 비교")
        )
        self.delta_settings.set_mode(self.monitor_mode_var.get())
        if circle_enabled:
            self.delta_settings.controls.grid_remove()
            self.detect_section.grid()
            self.grading_section.grid()
        else:
            self.detect_section.grid_remove()
            self.grading_section.grid_remove()
            self.delta_settings.controls.grid()

    def preview_source_size(self):
        title = self.obs_window_var.get().strip()
        hwnd = win32gui.FindWindow(None, title) if title else 0
        if not hwnd:
            raise ValueError(t("OBS 창 선택"))
        if win32gui.IsIconic(hwnd):
            raise ValueError(t("OBS 창 최소화 해제"))
        raw = cv2.cvtColor(capture_window(hwnd), cv2.COLOR_BGRA2BGR)
        rectangle, _ = detect_black_rectangle(raw)
        if rectangle is None:
            raise ValueError(t("검은 감지 영역 없음"))
        return rectangle[2], rectangle[3]

    def configure_styles(self):
        configure_theme(self)

    def show_config_warnings(self):
        messagebox.showwarning("Azusa Detector config", "\n".join(self.config_warnings))

    def handle_refresh_shortcut(self, event=None):
        if not self.monitor_running and not self.monitor_pending:
            self.refresh_windows()
        return "break"

    def refresh_windows(self, update_status=True):
        previous_obs_title = self.obs_window_var.get()
        previous_game_title = self.game_window_var.get()
        window_titles = list(dict.fromkeys(title for title in gw.getAllTitles() if title and not title.startswith(
            ("Azusa Detector", "Codex Computer Use", "ChatGPT is using your computer")) and title != "Program Manager"))
        self.obs_window_combo["values"] = window_titles
        self.game_window_combo["values"] = window_titles

        obs_windows = [title for title in window_titles if "OBS" in title.upper()]
        if previous_obs_title in window_titles:
            self.obs_window_var.set(previous_obs_title)
        elif obs_windows:
            self.obs_window_var.set(obs_windows[0])
        else:
            self.obs_window_var.set("")

        if previous_game_title in window_titles:
            self.game_window_var.set(previous_game_title)
        else:
            self.game_window_var.set("")

        if update_status:
            self.update_connection_status()

    def read_settings(self):
        if self._settings_cache is not None:
            return self._settings_cache
        config = deepcopy(self.config_data)
        circle = self.monitor_mode_var.get() == "circle"
        config["language"] = get_language()
        config["windows"] = {"obs_title": self.obs_window_var.get().strip(), "game_title": self.game_window_var.get().strip()}
        config["detect"]["circle_enabled"] = circle
        config["detect"]["circle_beep_enabled"] = self.circle_beep_var.get()
        if circle:
            config["detect"]["circle_radius"] = self.radius_var.get()
            config["grading"] = {"good_max": self.good_var.get(), "soso_max": self.soso_var.get()}
        config["auto"]["enabled"] = self.auto_enabled_var.get()
        config["auto"]["end_mode"] = self.auto_end_mode_var.get()
        if config["auto"]["enabled"] and config["auto"]["end_mode"] == "duration":
            config["auto"]["duration_sec"] = self.auto_duration_var.get()
        else:
            inactive_warnings = []
            duration = validate_recording_duration(self.auto_duration_var.get(), inactive_warnings)
            if not inactive_warnings:
                config["auto"]["duration_sec"] = duration
        delta = self.delta_settings.export()
        # Hidden controls never block live monitoring. Retain their last valid values.
        active = {"x_px", "y_px"} if delta["method"] == "axes" else {"distance_px"}
        for key in ("x_px", "y_px", "distance_px"):
            if circle or key not in active or not (delta["enabled"] or delta["guide_enabled"]):
                try:
                    value = float(delta[key])
                    if not math.isfinite(value) or value <= 0 or value > 1_000_000:
                        raise ValueError()
                except ValueError:
                    delta[key] = DEFAULT_DELTA[key]
        # Preserve legacy dimensions without letting them block the live-only UI.
        for key in ("preview_width", "preview_height"):
            try:
                if not 1 <= int(delta[key]) <= 100_000:
                    raise ValueError()
            except ValueError:
                delta[key] = DEFAULT_DELTA[key]
        config["delta_feedback"] = delta
        checked, warnings = validate_config(config)
        if warnings:
            raise ValueError(t("입력값 확인"))
        self._settings_cache = checked
        return checked

    def settings_changed(self, *_):
        self._settings_cache = None
        self.update_auto_controls()
        self.update_connection_status()
        if self._settings_log_after is not None:
            self.after_cancel(self._settings_log_after)
        self._settings_log_after = self.after(450, self.log_settings)

    def log_settings(self):
        self._settings_log_after = None
        try:
            current = self.read_settings()
        except ValueError:
            self.activity.emit("판정 설정값 확인", "error")
            return
        fields = (("windows", "obs_title", "OBS 화면"), ("windows", "game_title", "게임 창"),
                  ("detect", "circle_enabled", "모니터링 방식"), ("detect", "circle_radius", "원 반지름"),
                  ("detect", "circle_beep_enabled", "원형 비프음"), ("delta_feedback", "enabled", "이동량 비프음"),
                  ("delta_feedback", "guide_enabled", "측정 가이드"), ("delta_feedback", "method", "판정 방식"),
                  ("delta_feedback", "x_px", "X"), ("delta_feedback", "y_px", "Y"),
                  ("delta_feedback", "distance_px", "합산 거리"), ("grading", "good_max", "GOOD"),
                  ("grading", "soso_max", "SOSO"), ("auto", "enabled", "자동 기록"),
                  ("auto", "end_mode", "자동 종료"), ("auto", "duration_sec", "기록 시간"))
        for group, key, label in fields:
            value = current[group][key]
            if value == self._logged_settings.get(group, {}).get(key):
                continue
            values = {"name_key": label, "value": "ON" if value is True else "OFF" if value is False else value}
            if key == "circle_enabled":
                values.pop("value")
                values["value_key"] = "원형 판정" if value else "위치 추적"
            elif key == "method":
                values.pop("value")
                values["value_key"] = "X · Y 개별" if value == "axes" else "합산 거리"
            elif key == "end_mode":
                values.pop("value")
                values["value_key"] = "시간 지정" if value == "duration" else "타이머 감지"
            self.activity.emit("설정 · {name}: {value}", **values)
        self._logged_settings = deepcopy(current)

    def update_connection_status(self, *_):
        if not hasattr(self, "delta_settings") or not hasattr(self, "start_button"):
            return
        errors = {}
        for key, variable, combo in (("obs", self.obs_window_var, self.obs_window_combo), ("game", self.game_window_var, self.game_window_combo)):
            title = variable.get().strip()
            if not title:
                errors[key] = t("필수 · 창 선택")
            elif not win32gui.FindWindow(None, title):
                errors[key] = t("창 없음 · 다시 선택")
            combo.configure(style="Invalid.TCombobox" if key in errors else "TCombobox")
            if hasattr(self, "required_labels"):
                label = self.required_labels[key]
                label.configure(text=errors.get(key, ""))
                label.grid() if key in errors else label.grid_remove()
        try:
            self.read_settings()
        except ValueError:
            errors["values"] = t("판정 설정값 확인")
        invalid_fields = []
        circle = self.monitor_mode_var.get() == "circle"
        fields = [(self.radius_entry, self.radius_var, t("원 반지름"), circle, True)]
        delta = self.delta_settings
        for entry, variable, name, method in ((delta.x_entry, delta.x_px, "X", "axes"),
                                             (delta.y_entry, delta.y_px, "Y", "axes"),
                                             (delta.distance_entry, delta.distance_px, "px", "distance")):
            fields.append((entry, variable, name, not circle and (delta.enabled.get() or delta.guide_enabled.get()) and delta.method.get() == method, False))
        for entry, variable, name, active, integer in fields:
            valid = True
            if active:
                try:
                    number = int(variable.get()) if integer else float(variable.get())
                    valid = math.isfinite(number) and 0 < number <= 1_000_000
                except ValueError:
                    valid = False
            entry.configure(style="TEntry" if valid else "Invalid.TEntry")
            if not valid:
                invalid_fields.append(name)
        try:
            valid_grade = not circle or 0 < float(self.good_var.get()) < float(self.soso_var.get()) < 1
        except ValueError:
            valid_grade = False
        for entry in self.grading_entries:
            entry.configure(style="TEntry" if valid_grade else "Invalid.TEntry")
        if not valid_grade:
            invalid_fields.append("0 < GOOD < SOSO < 1")
        duration_warnings = []
        if self.auto_enabled_var.get() and self.auto_end_mode_var.get() == "duration":
            validate_recording_duration(self.auto_duration_var.get(), duration_warnings)
        self.auto_duration_entry.configure(style="Invalid.TEntry" if duration_warnings else "TEntry")
        if duration_warnings:
            invalid_fields.append(t("기록 시간 · 1–3600초"))
        if invalid_fields:
            errors["values"] = t("판정 설정값 확인") + ": " + ", ".join(invalid_fields)
        if hasattr(self, "input_error_var"):
            self.input_error_var.set(errors.get("values", ""))
            if "values" in errors:
                self.input_error_label.grid()
            else:
                self.input_error_label.grid_remove()
        if errors != self.required_errors and errors:
            self.activity.emit("오류: {error}", "error", error=" · ".join(errors.values()))
        self.required_errors = errors
        if self.monitor_pending:
            self.start_button.state(["disabled"])
            self.status_var.set(t("처리 중"))
        elif self.monitor_running:
            self.start_button.state(["!disabled"])
            self.status_var.set(t("입력값 확인 · 마지막 유효 설정 유지") if "values" in errors else t("설정 변경 실시간 적용"))
        else:
            self.start_button.state(["disabled"] if errors else ["!disabled"])
            names = [t("OBS 화면") if key == "obs" else t("게임 창") if key == "game" else t("판정 설정") for key in errors]
            self.status_var.set(t("필수 설정: {items}", items=" · ".join(names)) if errors else t("준비 완료 · 시작 시 설정 저장"))

    def toggle_settings(self):
        self.settings_visible = not self.settings_visible
        if self.settings_visible:
            self.left_scroller.grid()
            self.body.columnconfigure(0, minsize=360)
        else:
            self.left_scroller.grid_remove()
            self.body.columnconfigure(0, minsize=0)
        self.settings_toggle.configure(text=("‹  " + t("설정 접기")) if self.settings_visible else ("›  " + t("설정 펼치기")))

    def check_preview_source(self):
        if self.monitor_running or self.monitor_pending or self.closing:
            return
        title = self.obs_window_var.get().strip()
        hwnd = win32gui.FindWindow(None, title) if title else 0
        if not hwnd:
            self.refresh_windows(update_status=False)
            title = self.obs_window_var.get().strip()
            hwnd = win32gui.FindWindow(None, title) if title else 0
        available = bool(hwnd and not win32gui.IsIconic(hwnd))
        # Keep the single live panel active so source loss clears stale frames.
        self.live_preview.active = True
        self.last_source_available = available
        self.update_connection_status()

    def update_auto_controls(self):
        if not hasattr(self, "auto_end_controls"):
            return
        enabled = self.auto_enabled_var.get()
        editable = enabled and not (self.monitor_running or self.monitor_pending)
        for control in self.auto_end_controls:
            control.state(["!disabled"] if editable else ["disabled"])
        self.auto_duration_entry.state(["!disabled"] if editable else ["disabled"])
        if self.auto_end_mode_var.get() == "duration":
            self.auto_duration_row.grid() if enabled else self.auto_duration_row.grid_remove()
            hint = t("시작 감지 {a}–{b}초", a=self.config_data["auto"]["start_band"][0], b=self.config_data["auto"]["start_band"][1])
        else:
            self.auto_duration_row.grid_remove()
            cfg = self.config_data["auto"]
            hint = t("{a}–{b}초 시작 · {c}–{d}초 종료", a=cfg["start_band"][0], b=cfg["start_band"][1], c=cfg["end_band"][0], d=cfg["end_band"][1])
        self.auto_hint.configure(text=hint)

    def set_monitor_controls(self):
        running = self.monitor_running or self.monitor_pending
        for control in (self.obs_window_combo, self.game_window_combo, self.language_combo):
            control.configure(state="disabled" if running else "readonly")
        for control in self.mode_controls:
            control.state(["disabled"] if running else ["!disabled"])
        self.refresh_button.state(["disabled"] if running else ["!disabled"])
        self.update_auto_controls()
        self.phase_var.set(t("모니터링 중") if self.monitor_running else t("미리보기"))
        self.start_button.configure(text=t("모니터링 종료" if self.monitor_running else "모니터링 시작") + ("   ■" if self.monitor_running else "   →"))
        self.live_preview.update_actions()
        self.update_connection_status()

    def monitor_event(self, action, payload):
        if action in ("started", "stopped"):
            self.monitor_pending = False
            self.monitor_running = action == "started"
            self.set_monitor_controls()
            self.activity.emit("모니터링 시작" if action == "started" else "모니터링 종료")
        elif action == "closed":
            if self.closing:
                self.destroy()
        elif action == "error":
            self.monitor_pending = False
            self.closing = False
            self.monitor_running = payload["running"]
            self.set_monitor_controls()
            self.activity.emit("오류: {error}", "error", error=payload["message"])
            messagebox.showerror(t("작업 실패"), payload["message"])
        elif action == "saved":
            self.status_var.set(t("타이머 영역 저장"))
            self.live_preview.calibration_saved_until = time.monotonic() + 2
            self.activity.emit("타이머 영역 저장")

    def close_app(self):
        if self.closing:
            return
        self.closing = True
        self.monitor_pending = True
        self.update_connection_status()
        try:
            save_config(self.read_settings())
        except (ValueError, OSError) as error:
            self.activity.emit("오류: {error}", "error", error=str(error))
        self.live_preview.worker.send("close")

    def open_records(self):
        os.startfile(record_folder())

    def monitor_shortcut(self, event):
        if isinstance(event.widget, (ttk.Entry, ttk.Combobox, tk.Text)):
            return
        key = event.keysym.lower()
        if key == "escape" and self.monitor_running:
            self.start_monitoring()
        elif key == "d":
            self.live_preview.invoke_action("reset")
        elif key == "s":
            self.live_preview.invoke_action("sample")
        elif self.monitor_running and key in ("r", "m", "c"):
            self.live_preview.invoke_action({"r": "record", "m": "mute", "c": "calibrate"}[key])
        else:
            return
        return "break"

    def current_radius(self):
        try:
            return int(self.radius_var.get())
        except ValueError:
            return DEFAULT_CONFIG["detect"]["circle_radius"]

    def decrease_radius(self):
        self.radius_var.set(str(max(1, self.current_radius() - 1)))

    def increase_radius(self):
        self.radius_var.set(str(self.current_radius() + 1))

    def start_monitoring(self):
        if self.monitor_pending:
            return
        if self.monitor_running:
            try:
                self.config_data = self.read_settings()
                save_config(self.config_data)
            except (ValueError, OSError) as error:
                self.activity.emit("오류: {error}", "error", error=str(error))
            self.monitor_pending = True
            self.live_preview.worker.send("stop")
            self.update_connection_status()
            return
        self.update_connection_status()
        if self.required_errors:
            self.activity.emit("오류: {error}", "error", error=self.status_var.get())
            messagebox.showwarning(t("입력값 확인"), self.status_var.get())
            return
        config = self.read_settings()
        try:
            save_config(config)
        except OSError as error:
            self.activity.emit("오류: {error}", "error", error=str(error))
            messagebox.showerror(t("설정 저장 실패"), str(error))
            return
        self.config_data = config
        self.monitor_target = (config["windows"]["obs_title"], config["windows"]["game_title"], config)
        self.monitor_pending = True
        self.live_preview.worker.update(config, True)
        self.live_preview.worker.send("start", config)
        self.set_monitor_controls()



def detect_black_rectangle(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        max_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(max_contour)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        return (x, y, w, h), frame

    return None, frame


def draw_circle(frame, rect, circle_radius):
    x, y, w, h = rect
    circle_center = (x + w // 2, y + h // 2)
    cv2.circle(frame, circle_center, circle_radius, bgr("gold"), 2)
    return circle_center


def detect_white_point(frame, rect):
    """Find a white component's center throughout the play area, including inside the circle."""
    x, y, w, h = rect
    roi = frame[y : y + h, x : x + w]
    if roi.size == 0:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    white_pixels = cv2.inRange(hsv, WHITE_THRESHOLD_LOW, WHITE_THRESHOLD_HIGH)
    count, _, stats, centers = cv2.connectedComponentsWithStats(white_pixels)
    # Ignore isolated pixels and large white panels. Ambiguous similarly-sized
    # components are a missed detection, never an invented position.
    max_area = max(3, w * h * 0.05)
    candidates = [index for index in range(1, count) if 3 <= stats[index, cv2.CC_STAT_AREA] <= max_area]
    candidates.sort(key=lambda index: stats[index, cv2.CC_STAT_AREA], reverse=True)
    if not candidates:
        return None
    if len(candidates) > 1 and stats[candidates[0], cv2.CC_STAT_AREA] < 2 * stats[candidates[1], cv2.CC_STAT_AREA]:
        return None
    center = centers[candidates[0]]
    return float(center[0] + x), float(center[1] + y)


def judge_circle(point, rect, radius, enabled):
    if not enabled or point is None:
        return None
    x, y, w, h = rect
    return (point[0] - (x + w // 2)) ** 2 + (point[1] - (y + h // 2)) ** 2 > radius ** 2


class PointTracker:
    """Compare consecutive valid detections, retaining the reference across gaps."""

    def __init__(self):
        self.origin = None
        self.last_point = None
        self.last_seen_at = None
        self.relative = None
        self.delta = None
        self.delta_seconds = None
        self.detected = False

    def update(self, point, now):
        self.detected = point is not None
        if point is None:
            return
        if self.origin is None:
            self.origin = point
        self.relative = tuple(value - origin for value, origin in zip(point, self.origin))
        if self.last_point is not None:
            self.delta = tuple(value - previous for value, previous in zip(point, self.last_point))
            self.delta_seconds = now - self.last_seen_at
        self.last_point = point
        self.last_seen_at = now


def play_alert_sound(is_muted):
    if is_muted:
        return False
    if not os.path.exists(SOUND_FILE):
        raise OSError(t("알림음 파일 없음"))
    # Windows plays asynchronously: no thread or one-second sleep per alert.
    winsound.PlaySound(SOUND_FILE, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    return True


def capture_window(hwnd):
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        raise ValueError(t("캡처 영역 없음"))
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = save_dc = save_bitmap = None
    try:
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        save_bitmap = win32ui.CreateBitmap()
        save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(save_bitmap)
        if not windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3):
            raise ValueError(t("창 캡처 실패"))
        info = save_bitmap.GetInfo()
        pixels = save_bitmap.GetBitmapBits(True)
        return np.frombuffer(pixels, dtype="uint8").reshape((info["bmHeight"], info["bmWidth"], 4))
    finally:
        if save_dc is not None:
            save_dc.DeleteDC()
        if save_bitmap is not None:
            win32gui.DeleteObject(save_bitmap.GetHandle())
        if mfc_dc is not None:
            mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)


def seconds_from_digits(digits):
    digits = "".join(char for char in digits if char.isdigit())
    if not digits:
        return None
    value = int(digits[-2:]) if len(digits) >= 2 else int(digits)
    if 0 <= value <= 59:
        return value
    return None


def rect_iou(first, second):
    x1 = max(first["x"], second["x"])
    y1 = max(first["y"], second["y"])
    x2 = min(first["x"] + first["w"], second["x"] + second["w"])
    y2 = min(first["y"] + first["h"], second["y"] + second["h"])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    if intersection == 0:
        return 0.0
    first_area = first["w"] * first["h"]
    second_area = second["w"] * second["h"]
    return intersection / float(first_area + second_area - intersection)


class TimerDetector:
    def __init__(self, config):
        self.config = config
        self.templates = self.load_digit_templates()
        self.ocr_enabled = config["auto"].get("ocr_fallback", False)
        self.ocr_available = None
        self.last_ocr_at = 0.0

    def load_digit_templates(self):
        templates = {}
        search_dirs = [EXTERNAL_DIGIT_DIR, resource_path(os.path.join("assets", "digits"))]

        for digit in range(10):
            filename = f"{digit}.png"
            for directory in search_dirs:
                path = os.path.join(directory, filename)
                if not os.path.exists(path):
                    continue
                template = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                if template is None or template.size == 0:
                    continue
                templates[str(digit)] = self.binarize_timer_image(template)
                break
        return templates

    @staticmethod
    def binarize_timer_image(image):
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        _, binary = cv2.threshold(gray, 185, 255, cv2.THRESH_BINARY)
        return binary

    def crop_timer_roi(self, frame, rect):
        if rect is None:
            return None, None

        x, y, w, h = rect
        roi_config = self.config["timer_roi"]
        roi_x = x + int(w * roi_config["x_ratio"])
        roi_y = y + int(h * roi_config["y_ratio"])
        roi_w = max(1, int(w * roi_config["w_ratio"]))
        roi_h = max(1, int(h * roi_config["h_ratio"]))

        frame_h, frame_w = frame.shape[:2]
        roi_x = max(0, min(roi_x, frame_w - 1))
        roi_y = max(0, min(roi_y, frame_h - 1))
        roi_w = max(1, min(roi_w, frame_w - roi_x))
        roi_h = max(1, min(roi_h, frame_h - roi_y))
        return frame[roi_y : roi_y + roi_h, roi_x : roi_x + roi_w], (roi_x, roi_y, roi_w, roi_h)

    def read_seconds(self, frame, rect, now):
        roi, roi_rect = self.crop_timer_roi(frame, rect)
        if roi is None or roi.size == 0:
            return None, roi_rect, None

        template_value = self.read_with_templates(roi)
        if template_value is not None:
            return template_value, roi_rect, "template"

        if self.ocr_enabled and now - self.last_ocr_at >= 0.35:
            self.last_ocr_at = now
            ocr_value = self.read_with_ocr(roi)
            if ocr_value is not None:
                return ocr_value, roi_rect, "ocr"

        return None, roi_rect, None

    def read_with_templates(self, roi):
        if not self.templates:
            return None

        binary = self.binarize_timer_image(roi)
        boxes = self.find_digit_boxes(binary)
        if len(boxes) < 2:
            return None

        digits = []
        for x, y, w, h in boxes:
            candidate = binary[y : y + h, x : x + w]
            digit, score = self.match_digit_candidate(candidate)
            if digit is not None and score >= DIGIT_CANDIDATE_SCORE_MIN:
                digits.append((x, digit, score))

        if len(digits) < 2:
            return None

        digits.sort(key=lambda item: item[0])
        return seconds_from_digits("".join(digit for _, digit, _ in digits))

    @staticmethod
    def find_digit_boxes(binary):
        roi_h, roi_w = binary.shape[:2]
        min_h = max(6, int(roi_h * 0.18))
        max_h = max(min_h, int(roi_h * 0.65))
        max_w = max(5, int(roi_w * 0.25))
        min_y = int(roi_h * 0.35)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
        boxes = []
        for label in range(1, num_labels):
            x, y, w, h, area = stats[label]
            if y >= min_y and min_h <= h <= max_h and 2 <= w <= max_w and area >= 8:
                boxes.append((int(x), int(y), int(w), int(h)))
        boxes.sort(key=lambda item: item[0])
        return boxes

    def match_digit_candidate(self, candidate):
        best_digit = None
        best_score = -1.0
        candidate_h, candidate_w = candidate.shape[:2]

        for digit, template in self.templates.items():
            resized = cv2.resize(template, (candidate_w, candidate_h), interpolation=cv2.INTER_AREA)
            result = cv2.matchTemplate(candidate, resized, cv2.TM_CCOEFF_NORMED)
            score = float(result[0][0])
            if score > best_score:
                best_digit = digit
                best_score = score

        return best_digit, best_score

    def read_with_ocr(self, roi):
        if self.ocr_available is False:
            return None

        try:
            import pytesseract
        except Exception:
            self.ocr_available = False
            return None

        self.ocr_available = True
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        try:
            text = pytesseract.image_to_string(
                binary,
                config="--psm 7 -c tessedit_char_whitelist=0123456789:",
            )
        except Exception:
            return None
        return seconds_from_digits(text)


class AutoStateMachine:
    IDLE = "IDLE"
    RECORDING = "RECORDING"
    COOLDOWN = "COOLDOWN"

    def __init__(self, config):
        self.config = config["auto"]
        self.state = self.IDLE
        self.start_hits = 0
        self.end_hits = 0
        self.last_seen_at = None
        self.cooldown_until = 0.0
        self.last_grade = None
        self.last_seconds = None
        self.end_mode = self.config.get("end_mode", "duration")
        self.started_at = None
        self.deadline = None

    @property
    def enabled(self):
        return self.config["enabled"]

    def in_band(self, seconds, band_name):
        if seconds is None:
            return False
        low, high = self.config[band_name]
        return low <= seconds <= high

    def tick_cooldown(self, now):
        if self.state == self.COOLDOWN and now >= self.cooldown_until:
            self.state = self.IDLE
            self.last_grade = None
            self.start_hits = 0
            self.end_hits = 0

    def maybe_start(self, timer_seconds, now, is_recording):
        if not self.enabled:
            return False

        self.tick_cooldown(now)
        if timer_seconds is not None:
            self.last_seconds = timer_seconds

        if self.state != self.IDLE or is_recording:
            self.start_hits = 0
            return False

        if self.in_band(timer_seconds, "start_band"):
            self.start_hits += 1
        else:
            self.start_hits = 0

        if self.start_hits >= self.config["debounce_frames"]:
            self.state = self.RECORDING
            self.start_hits = 0
            self.end_hits = 0
            self.last_seen_at = now
            self.end_mode = self.config.get("end_mode", "duration")
            self.started_at = now
            self.deadline = now + self.config.get("duration_sec", 60) if self.end_mode == "duration" else None
            return True
        return False

    def maybe_finish(self, timer_seconds, now, is_recording, recording_source):
        if not self.enabled:
            return None

        self.tick_cooldown(now)
        if timer_seconds is not None:
            self.last_seconds = timer_seconds

        if self.state != self.RECORDING or not is_recording or recording_source != "auto":
            return None

        # A fixed deadline ignores both end digits and any gaps in timer capture.
        # Capture this once at start so setting changes cannot alter an active run.
        if self.end_mode == "duration":
            return "duration elapsed" if self.deadline is not None and now >= self.deadline else None

        if timer_seconds is not None:
            self.last_seen_at = now
            if self.in_band(timer_seconds, "end_band"):
                self.end_hits += 1
            else:
                self.end_hits = 0
            if self.end_hits >= self.config["debounce_frames"]:
                return "timer end"
        elif self.last_seen_at is not None and now - self.last_seen_at > self.config["grace_sec"]:
            return "timer lost"

        return None

    def remaining(self, now):
        if self.state == self.RECORDING and self.deadline is not None:
            return max(0.0, self.deadline - now)
        return None

    def record_stopped(self, result, now):
        if not self.enabled:
            return
        if self.state == self.RECORDING:
            self.state = self.COOLDOWN
            self.cooldown_until = now + self.config["cooldown_sec"]
            self.last_grade = result["grade"] if result else None
            self.start_hits = 0
            self.end_hits = 0
            self.started_at = None
            self.deadline = None

    def label(self, session):
        if not self.enabled:
            return "AUTO: OFF"
        if self.state == self.COOLDOWN:
            grade = self.last_grade or "DONE"
            return f"AUTO: DONE({grade})"
        if session is not None and session.source == "auto":
            if self.last_seconds is None:
                return "AUTO: REC --"
            return f"AUTO: REC 00:{self.last_seconds:02d}"
        return f"AUTO: {self.state}"


class SessionRecorder:
    def __init__(self, config, source):
        self.config = config
        self.source = source
        self.timestamp = datetime.now()
        self.start_time = datetime.now()
        self.data = []
        self.total_frames = 0
        self.detected_frames = 0
        self.graded_frames = 0
        self.outside_frames = 0
        self.beep_count = 0
        self.max_outside_s = 0.0
        self.current_outside_started_at = None
        self.last_outside_at = None

    def close_outside_interval(self, at_time):
        if self.current_outside_started_at is not None:
            self.max_outside_s = max(self.max_outside_s, at_time - self.current_outside_started_at)
            self.current_outside_started_at = None

    def add_frame(self, is_outside, white_point, rectangle, beep_event, tracker, circle_enabled, delta_over=None):
        current_time = (datetime.now() - self.start_time).total_seconds()
        x, y, w, h = rectangle

        self.total_frames += 1
        if white_point is not None:
            self.detected_frames += 1
        if is_outside is not None:
            self.graded_frames += 1
        if is_outside:
            self.outside_frames += 1

        if beep_event:
            self.beep_count += 1

        if is_outside:
            if self.current_outside_started_at is None:
                self.current_outside_started_at = current_time
            self.last_outside_at = current_time
        elif self.current_outside_started_at is not None:
            # Unknown/off frames must not extend an observed outside streak.
            self.close_outside_interval(self.last_outside_at if is_outside is None else current_time)

        if white_point is not None:
            point = white_point
            relative = tracker.relative
            delta = tracker.delta or (None, None)
            delta_seconds = tracker.delta_seconds
        else:
            point = relative = delta = (None, None)
            delta_seconds = None
        self.data.append([
            current_time, is_outside, *point, w, h,
            white_point is not None, circle_enabled, *relative, *delta, delta_seconds,
            math.hypot(*delta) if delta[0] is not None else None,
            not circle_enabled and self.config["delta_feedback"]["enabled"],
            self.config["delta_feedback"]["method"],
            self.config["delta_feedback"]["x_px"], self.config["delta_feedback"]["y_px"],
            self.config["delta_feedback"]["distance_px"], delta_over,
        ])

    def finish(self):
        duration_s = (datetime.now() - self.start_time).total_seconds()
        if self.current_outside_started_at is not None:
            self.max_outside_s = max(self.max_outside_s, duration_s - self.current_outside_started_at)
            self.current_outside_started_at = None

        outside_ratio = self.outside_frames / self.graded_frames if self.graded_frames else None
        good_max = self.config["grading"]["good_max"]
        soso_max = self.config["grading"]["soso_max"]
        if outside_ratio is None:
            grade = "N/A"
        elif outside_ratio <= good_max:
            grade = "GOOD"
        elif outside_ratio <= soso_max:
            grade = "SOSO"
        else:
            grade = "BAD"

        return {
            "timestamp": self.timestamp,
            "duration_s": duration_s,
            "total_frames": self.total_frames,
            "detected_frames": self.detected_frames,
            "graded_frames": self.graded_frames,
            "outside_frames": self.outside_frames,
            "outside_ratio": outside_ratio,
            "grade": grade,
            "good_max": good_max,
            "soso_max": soso_max,
            "beep_count": self.beep_count,
            "max_outside_s": self.max_outside_s,
            "source": self.source,
            "record_data": self.data,
        }


def record_folder():
    folder_name = os.path.join(app_base_dir(), "azusa_record")
    os.makedirs(folder_name, exist_ok=True)
    return folder_name


def save_record_data(data, rectangle):
    folder_name = record_folder()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = os.path.join(folder_name, f"record_{timestamp}.csv")

    rect_w = rectangle[2] if rectangle else 0
    rect_h = rectangle[3] if rectangle else 0
    with open(filename, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Rectangle Size", f"{rect_w}x{rect_h}"])
        writer.writerow([
            "Time (s)", "Is Outside", "X", "Y", "Rectangle Width", "Rectangle Height",
            "Detected", "Circle Enabled", "Relative X", "Relative Y", "Delta X", "Delta Y", "Delta Time (s)",
            "Delta Distance (px)", "Delta Feedback Enabled", "Delta Threshold Mode",
            "Delta Limit X (px)", "Delta Limit Y (px)", "Delta Limit Distance (px)", "Delta Over Threshold",
        ])
        writer.writerows(data)
    print(f"Record saved to {filename}")
    return filename


def append_session_summary(result):
    # Keep the legacy summary schema intact; v2 includes a graded-frame denominator.
    filename = os.path.join(record_folder(), "sessions_v2.csv")
    write_header = not os.path.exists(filename) or os.path.getsize(filename) == 0
    header = [
        "timestamp",
        "duration_s",
        "total_frames",
        "detected_frames",
        "graded_frames",
        "outside_frames",
        "outside_ratio",
        "grade",
        "good_max",
        "soso_max",
        "beep_count",
        "max_outside_s",
        "source",
    ]
    row = [
        result["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
        f"{result['duration_s']:.3f}",
        result["total_frames"],
        result["detected_frames"],
        result["graded_frames"],
        result["outside_frames"],
        f"{result['outside_ratio']:.6f}" if result["outside_ratio"] is not None else "",
        result["grade"],
        result["good_max"],
        result["soso_max"],
        result["beep_count"],
        f"{result['max_outside_s']:.3f}",
        result["source"],
    ]

    with open(filename, "a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if write_header:
            writer.writerow(header)
        writer.writerow(row)
    print(f"Session saved to {filename}")


def finish_recording(session, rectangle):
    result = session.finish()
    save_record_data(result["record_data"], rectangle)
    append_session_summary(result)
    return result


def save_timer_calibration(frame, rectangle, timer_detector):
    roi, _ = timer_detector.crop_timer_roi(frame, rectangle)
    if roi is None or roi.size == 0:
        return None

    folder = os.path.join(EXTERNAL_DIGIT_DIR, "calibration")
    os.makedirs(folder, exist_ok=True)
    filename = os.path.join(folder, f"timer_roi_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    encoded, png = cv2.imencode(".png", roi)
    if encoded:
        png.tofile(filename)
        return filename
    return None


def draw_alpha_rect(frame, x1, y1, x2, y2, color, alpha=0.72):
    height, width = frame.shape[:2]
    x1 = max(0, min(width - 1, int(x1)))
    y1 = max(0, min(height - 1, int(y1)))
    x2 = max(0, min(width, int(x2)))
    y2 = max(0, min(height, int(y2)))
    if x2 <= x1 or y2 <= y1:
        return

    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def draw_text(frame, text, x, y, scale=0.55, color=(235, 240, 245), thickness=1):
    text = overlay_text(text)
    if not text.isascii():
        unicode_text.draw(frame, text, x, y, scale, color)
        return
    cv2.putText(frame, text, (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def text_width(text, scale=0.55, thickness=1):
    text = overlay_text(text)
    if not text.isascii():
        return unicode_text.width(text, scale)
    size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thickness)
    return size[0]


def fit_text_scale(text, max_width, preferred_scale=0.55, min_scale=0.38, thickness=1):
    scale = preferred_scale
    while scale > min_scale and text_width(text, scale, thickness) > max_width:
        scale -= 0.03
    return max(min_scale, scale)


def draw_badge(frame, x, y, text, bg_color, fg_color=(245, 248, 252), scale=0.48):
    pad_x = 9
    pad_y = 5
    label_w = text_width(text, scale, 1)
    label_h = 18
    x2 = int(x + label_w + pad_x * 2)
    y2 = int(y + label_h + pad_y * 2)
    draw_alpha_rect(frame, x, y, x2, y2, bg_color, 0.88)
    cv2.rectangle(frame, (int(x), int(y)), (x2, y2), tuple(min(255, c + 36) for c in bg_color), 1)
    draw_text(frame, text, x + pad_x, y + pad_y + 14, scale, fg_color, 1)
    return x2


def draw_keycap(frame, x, y, key, width, height, accent_color):
    draw_alpha_rect(frame, x, y, x + width, y + height, (42, 49, 60), 0.94)
    cv2.rectangle(frame, (int(x), int(y)), (int(x + width), int(y + height)), accent_color, 1)
    text_scale = fit_text_scale(key, width - 8, 0.44, 0.32, 1)
    text_size, baseline = cv2.getTextSize(key, cv2.FONT_HERSHEY_SIMPLEX, text_scale, 1)
    text_x = x + (width - text_size[0]) / 2
    text_y = y + (height + text_size[1]) / 2 - 2
    draw_text(frame, key, text_x, text_y, text_scale, (248, 250, 252), 1)


def draw_shortcut_guide(frame, margin, circle_enabled=True, delta_enabled=False):
    height, width = frame.shape[:2]
    controls = [
        ("Q/ESC", "Back to setup"),
        ("R", "Record on/off"),
    ]
    if circle_enabled or delta_enabled:
        controls.append(("M", "Mute"))
    if circle_enabled:
        controls.append(("+/-", "Radius"))
    controls.append(("C", "Save game timer ROI"))

    bg = bgr("deep")
    border = bgr("purple")
    accent = bgr("gold")
    muted = bgr("muted")
    text = bgr("silver")
    max_w = width - margin * 2
    key_scale = 0.44
    label_scale = 0.45
    item_gap = 16
    row_gap = 8
    row_h = 26
    title_h = 25

    items = []
    for key, label in controls:
        key_w = max(32, text_width(key, key_scale, 1) + 18)
        label_w = text_width(label, label_scale, 1)
        items.append((key, label, key_w, label_w, key_w + label_w + 8))

    rows = [[]]
    current_w = 0
    for item in items:
        item_w = item[4]
        next_w = item_w if not rows[-1] else current_w + item_gap + item_w
        if rows[-1] and next_w > max_w - 28:
            rows.append([item])
            current_w = item_w
        else:
            rows[-1].append(item)
            current_w = next_w

    content_w = max(
        min(max_w - 28, sum(item[4] for item in row) + item_gap * max(0, len(row) - 1))
        for row in rows
    )
    guide_w = min(max_w, content_w + 28)
    guide_h = title_h + len(rows) * row_h + max(0, len(rows) - 1) * row_gap + 16
    x1 = margin
    y1 = max(margin, height - margin - guide_h)
    x2 = x1 + guide_w
    y2 = y1 + guide_h

    draw_alpha_rect(frame, x1, y1, x2, y2, bg, 0.82)
    cv2.rectangle(frame, (x1, y1), (x2, y2), border, 1)
    draw_text(frame, "CONTROLS", x1 + 14, y1 + 20, 0.42, muted, 1)

    row_y = y1 + title_h + 6
    for row in rows:
        cursor_x = x1 + 14
        for key, label, key_w, label_w, item_w in row:
            draw_keycap(frame, cursor_x, row_y, key, key_w, 22, accent)
            draw_text(frame, label, cursor_x + key_w + 8, row_y + 16, label_scale, text, 1)
            cursor_x += item_w + item_gap
        row_y += row_h + row_gap


def draw_result_card(frame, result):
    if result is None:
        return

    grade = result["grade"]
    ratio_text = f"{result['outside_ratio'] * 100:.1f}%" if result["outside_ratio"] is not None else "--"
    title = f"{grade}"
    detail = (
        f"outside {ratio_text}  |  {result['outside_frames']}/{result['graded_frames']} judged frames"
        if result["graded_frames"] else "No judged frames (circle off or no detection)"
    )
    extra = f"beeps {result['beep_count']}  |  max outside {result['max_outside_s']:.2f}s"

    grade_colors = {
        "GOOD": (92, 220, 126),
        "SOSO": (64, 202, 255),
        "BAD": (86, 118, 255),
    }
    accent = grade_colors.get(grade, (230, 230, 230))

    height, width = frame.shape[:2]
    margin = max(14, int(min(width, height) * 0.018))
    card_w = min(max(440, width // 2 - 20), width - margin * 2)
    card_h = 132
    x1 = width - margin - card_w
    y1 = margin if x1 >= 480 else margin + 285
    x2 = x1 + card_w
    y2 = y1 + card_h

    draw_alpha_rect(frame, x1, y1, x2, y2, (18, 22, 28), 0.88)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (70, 82, 98), 1)
    cv2.rectangle(frame, (x1, y1), (x1 + 6, y2), accent, -1)
    draw_text(frame, title, x1 + 24, y1 + 45, 1.1, accent, 2)
    draw_text(frame, detail, x1 + 24, y1 + 78, fit_text_scale(detail, card_w - 48, 0.62), (238, 242, 246), 1)
    draw_text(frame, extra, x1 + 24, y1 + 108, 0.52, (170, 180, 192), 1)


def draw_hud(frame, circle_radius, session, is_muted, auto_label, timer_seconds, timer_method,
             status_message, last_result=None, circle_enabled=True, tracker=None, delta_feedback=None):
    height, width = frame.shape[:2]
    margin = max(12, int(min(width, height) * 0.014))
    panel_w = min(460, width - margin * 2)
    panel_h = 258 if not status_message else 284
    x1 = margin
    y1 = margin
    x2 = x1 + panel_w
    y2 = y1 + panel_h

    bg = bgr("deep")
    border = bgr("purple")
    text = bgr("silver")
    muted = bgr("muted")
    accent = bgr("gold")
    red = bgr("pink")
    green = bgr("safe")
    blue = bgr("lilac")
    gray = bgr("border")

    draw_alpha_rect(frame, x1, y1, x2, y2, bg, 0.78)
    cv2.rectangle(frame, (x1, y1), (x2, y2), border, 1)
    draw_text(frame, "AZUSA DETECTOR", x1 + 14, y1 + 24, 0.48, muted, 1)
    mode_label = "MODE: CIRCLE JUDGING" if circle_enabled else "MODE: POSITION ONLY"
    draw_text(frame, mode_label, x1 + 14, y1 + 55, 0.55, green if circle_enabled else accent)

    if session is not None:
        elapsed_time = (datetime.now() - session.start_time).total_seconds()
        minutes, seconds = divmod(int(elapsed_time), 60)
        rec_text = f"REC {minutes:02d}:{seconds:02d} {session.source.upper()}"
        rec_color = red
    else:
        rec_text = "IDLE"
        rec_color = gray

    timer_text = "--"
    if timer_seconds is not None:
        timer_text = f"00:{timer_seconds:02d}"
    if timer_method:
        timer_text = f"{timer_text} {timer_method.upper()}"

    auto_text = auto_label.replace("AUTO:", "AUTO").strip()
    auto_color = blue
    if "OFF" in auto_text:
        auto_color = gray
    elif "DONE" in auto_text:
        auto_color = green
    elif "REC" in auto_text:
        auto_color = red

    badge_y = y1 + 76
    next_x = draw_badge(frame, x1 + 14, badge_y, rec_text, rec_color)
    if next_x + 118 < x2:
        next_x = draw_badge(frame, next_x + 8, badge_y, auto_text, auto_color)
    if next_x + 94 < x2:
        draw_badge(frame, next_x + 8, badge_y, timer_text, (52, 62, 74))

    row_y = y1 + 126
    if circle_enabled:
        draw_text(frame, f"Radius {circle_radius}", x1 + 14, row_y, 0.52, text, 1)
        mute_label = "Muted ON" if is_muted else "Muted OFF"
        mute_color = (80, 96, 230) if is_muted else muted
        draw_text(frame, mute_label, x1 + 130, row_y, 0.52, mute_color, 1)
    else:
        delta_label = threshold_label(delta_feedback.config) if delta_feedback else "Delta feedback OFF"
        if is_muted:
            delta_label += " [MUTED]"
        draw_text(frame, delta_label, x1 + 14, row_y, fit_text_scale(delta_label, panel_w - 28, 0.46), muted)
    if tracker is not None:
        tracking_label = "TRACKING" if tracker.detected else "NO DETECTION - holding last values"
        delta_alert = delta_feedback is not None and delta_feedback.visible(time.monotonic())
        if delta_alert and tracker.detected:
            dx, dy = delta_feedback.last_alert_delta
            tracking_label = f"DELTA ALERT: X {dx:+.1f} Y {dy:+.1f} px"
        draw_text(frame, tracking_label, x1 + 14, y1 + 151, fit_text_scale(tracking_label, panel_w - 28, 0.46),
                  (80, 100, 255) if delta_alert else (green if tracker.detected else accent))
        position_text = "Position: -- (waiting for first detection)"
        if tracker.relative is not None:
            position_text = f"Position: X {tracker.relative[0]:+.1f}  Y {tracker.relative[1]:+.1f} px"
        draw_text(frame, position_text, x1 + 14, y1 + 176, fit_text_scale(position_text, panel_w - 28), text)
        delta_text = "Delta: -- (waiting for next detection)"
        if tracker.delta is not None:
            delta_text = f"Delta: X {tracker.delta[0]:+.1f}  Y {tracker.delta[1]:+.1f} px"
        draw_text(frame, delta_text, x1 + 14, y1 + 201, fit_text_scale(delta_text, panel_w - 28), text)
        gap_text = "Axes: right +X, down +Y"
        if tracker.delta_seconds is not None:
            gap_text += f"  |  dt {tracker.delta_seconds:.3f}s"
        draw_text(frame, gap_text, x1 + 14, y1 + 222, 0.40, muted)
    if last_result is not None:
        # 결과 카드(3초)가 사라진 뒤에도 마지막 세션 결과를 항상 확인 가능
        grade_colors = {"GOOD": (92, 220, 126), "SOSO": (64, 202, 255), "BAD": (86, 118, 255)}
        ratio = last_result["outside_ratio"]
        last_text = f"Last {last_result['grade']}" + (f" {ratio * 100:.1f}%" if ratio is not None else " (no judged frames)")
        draw_text(frame, last_text, x1 + 14, y1 + 244, 0.44, grade_colors.get(last_result["grade"], muted), 1)

    if status_message:
        status_scale = fit_text_scale(status_message, panel_w - 28, 0.48, 0.36)
        draw_text(frame, status_message, x1 + 14, y1 + 271, status_scale, accent, 1)

    draw_shortcut_guide(frame, margin, circle_enabled, bool(delta_feedback and delta_feedback.config["enabled"]))


def set_status(message):
    return message, time.time() + STATUS_OVERLAY_SEC


def initialize_display_window(frame):
    cv2.namedWindow(DISPLAY_WINDOW_NAME, cv2.WINDOW_NORMAL)
    height, width = frame.shape[:2]
    scale = min(DISPLAY_MAX_WIDTH / width, DISPLAY_MAX_HEIGHT / height, 1.0)
    cv2.resizeWindow(DISPLAY_WINDOW_NAME, max(320, int(width * scale)), max(240, int(height * scale)))


def find_window_handle(window_title, label):
    windows = gw.getWindowsWithTitle(window_title)
    if not windows:
        print(f"{label} window not found: {window_title}")
        return None

    hwnd = win32gui.FindWindow(None, window_title)
    if not hwnd:
        print(f"{label} window handle not found: {window_title}")
        return None
    return hwnd


def full_frame_rect(frame):
    height, width = frame.shape[:2]
    return (0, 0, width, height)


def main(obs_window_title, game_window_title, config):
    """Compatibility entry point: monitoring is hosted by the main Tk window."""
    config = deepcopy(config)
    config["windows"] = {"obs_title": obs_window_title, "game_title": game_window_title}
    app = App(config, [])
    app.after_idle(app.start_monitoring)
    app.mainloop()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        from self_check import run_self_check

        raise SystemExit(run_self_check(sys.modules[__name__]))
    if getattr(sys, "frozen", False):
        hide_console()
    loaded_config, loaded_warnings = load_config()
    app = App(loaded_config, loaded_warnings)
    if "--sample" in sys.argv:
        app.after(200, lambda: app.live_preview.invoke_action("sample"))
    app.mainloop()
