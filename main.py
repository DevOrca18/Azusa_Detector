import csv
import json
import os
import sys
import threading
import time
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


WHITE_THRESHOLD_LOW = np.array([0, 0, 200])
WHITE_THRESHOLD_HIGH = np.array([180, 25, 255])

DEFAULT_CONFIG = {
    "grading": {"good_max": 0.05, "soso_max": 0.15},
    "auto": {
        "enabled": True,
        "start_band": [55, 59],
        "end_band": [0, 1],
        "debounce_frames": 3,
        "grace_sec": 2.0,
        "cooldown_sec": 5.0,
        "ocr_fallback": False,
    },
    "timer_roi": {"x_ratio": 0.42, "y_ratio": -0.98, "w_ratio": 0.13, "h_ratio": 0.08},
    "detect": {"circle_radius": 45},
}

DIGIT_CANDIDATE_SCORE_MIN = 0.25
RESULT_OVERLAY_SEC = 3.0
STATUS_OVERLAY_SEC = 2.0


def hide_console():
    try:
        console_window = win32gui.GetForegroundWindow()
        win32gui.ShowWindow(console_window, win32con.SW_HIDE)
    except Exception:
        pass


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


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


def validate_config(config):
    warnings = []
    merged = deep_merge(DEFAULT_CONFIG, config)

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
    merged["auto"] = {
        "enabled": coerce_bool(auto_config.get("enabled"), auto_default["enabled"], warnings, "auto.enabled"),
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
        "circle_radius": coerce_int(
            detect_config.get("circle_radius"),
            detect_default["circle_radius"],
            warnings,
            "detect.circle_radius",
            minimum=1,
        )
    }

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
        super().__init__(theme="arc")

        self.config_data = config
        self.config_warnings = config_warnings

        self.title("Azusa Detector")
        self.geometry("430x500")

        self.style = ttk.Style(self)
        self.style.configure("TLabel", font=("Helvetica", 11))
        self.style.configure("TButton", font=("Helvetica", 11))

        self.window_var = tk.StringVar()
        self.radius_var = tk.StringVar(value=str(config["detect"]["circle_radius"]))
        self.good_var = tk.StringVar(value=str(config["grading"]["good_max"]))
        self.soso_var = tk.StringVar(value=str(config["grading"]["soso_max"]))
        self.auto_enabled_var = tk.BooleanVar(value=config["auto"]["enabled"])
        self.status_var = tk.StringVar(value="Ready")

        main_frame = ttk.Frame(self, padding="20 20 20 20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Azusa Detector", font=("Helvetica", 18, "bold")).pack(pady=10)

        ttk.Label(main_frame, text="Select Window:").pack(pady=5)
        window_frame = ttk.Frame(main_frame)
        window_frame.pack(fill=tk.X, pady=5)
        self.window_combo = ttk.Combobox(window_frame, textvariable=self.window_var, width=30)
        self.window_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(window_frame, text="Refresh", command=self.refresh_windows, width=9).pack(side=tk.LEFT)
        self.refresh_windows(update_status=False)

        ttk.Label(main_frame, text="Circle Radius:").pack(pady=(14, 5))
        radius_frame = ttk.Frame(main_frame)
        radius_frame.pack(pady=5)
        ttk.Entry(radius_frame, textvariable=self.radius_var, width=7).pack(side=tk.LEFT, padx=5)
        ttk.Button(radius_frame, text="-", command=self.decrease_radius, width=3).pack(side=tk.LEFT)
        ttk.Button(radius_frame, text="+", command=self.increase_radius, width=3).pack(side=tk.LEFT)

        grading_frame = ttk.LabelFrame(main_frame, text="Grading")
        grading_frame.pack(fill=tk.X, pady=(14, 5))
        ttk.Label(grading_frame, text="GOOD max").grid(row=0, column=0, sticky=tk.W, padx=10, pady=6)
        ttk.Entry(grading_frame, textvariable=self.good_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=10, pady=6)
        ttk.Label(grading_frame, text="SOSO max").grid(row=1, column=0, sticky=tk.W, padx=10, pady=6)
        ttk.Entry(grading_frame, textvariable=self.soso_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=10, pady=6)

        auto_frame = ttk.LabelFrame(main_frame, text="Auto Timer")
        auto_frame.pack(fill=tk.X, pady=(10, 5))
        ttk.Checkbutton(auto_frame, text="Enable auto start/finish", variable=self.auto_enabled_var).pack(
            anchor=tk.W, padx=10, pady=8
        )

        ttk.Button(main_frame, text="Start Monitoring", command=self.start_monitoring, style="Accent.TButton").pack(
            pady=20
        )

        ttk.Label(main_frame, textvariable=self.status_var, font=("Helvetica", 10, "italic")).pack(pady=10)

        if self.config_warnings:
            self.after(250, self.show_config_warnings)

    def show_config_warnings(self):
        messagebox.showwarning("Azusa Detector config", "\n".join(self.config_warnings))

    def refresh_windows(self, update_status=True):
        previous_title = self.window_var.get()
        window_titles = [title for title in gw.getAllTitles() if title]
        self.window_combo["values"] = window_titles

        if previous_title in window_titles:
            self.window_var.set(previous_title)
        else:
            obs_windows = [title for title in window_titles if "OBS" in title]
            if obs_windows:
                self.window_var.set(obs_windows[0])
            elif window_titles:
                self.window_var.set(window_titles[0])
            else:
                self.window_var.set("")

        if update_status:
            self.status_var.set(f"Window list refreshed ({len(window_titles)} found)")

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
        window_title = self.window_var.get().strip()
        if not window_title:
            messagebox.showwarning("Azusa Detector", "Select a target window first.")
            return

        updated_config = deepcopy(self.config_data)
        updated_config["detect"]["circle_radius"] = self.radius_var.get()
        updated_config["grading"]["good_max"] = self.good_var.get()
        updated_config["grading"]["soso_max"] = self.soso_var.get()
        updated_config["auto"]["enabled"] = self.auto_enabled_var.get()

        validated_config, warnings = validate_config(updated_config)
        if warnings:
            messagebox.showwarning("Azusa Detector config", "\n".join(warnings))

        save_config(validated_config)
        self.status_var.set("Monitoring started...")
        self.destroy()
        threading.Thread(target=main, args=(window_title, validated_config)).start()


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
    cv2.circle(frame, circle_center, circle_radius, (0, 255, 255), 2)
    return circle_center


def check_white_point_outside_circle(frame, rect, circle_center, circle_radius):
    x, y, w, h = rect
    roi = frame[y : y + h, x : x + w]

    mask = np.zeros(roi.shape[:2], dtype=np.uint8)
    cv2.circle(mask, (circle_center[0] - x, circle_center[1] - y), circle_radius, 255, -1)

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    white_pixels = cv2.inRange(hsv, WHITE_THRESHOLD_LOW, WHITE_THRESHOLD_HIGH)
    outside_white_pixels = cv2.bitwise_and(white_pixels, cv2.bitwise_not(mask))

    white_points = cv2.findNonZero(outside_white_pixels)
    if white_points is not None:
        point = white_points[0][0]
        return True, (point[0] + x, point[1] + y)
    return False, None


def play_alert_sound(is_muted):
    if is_muted:
        return
    if not os.path.exists(SOUND_FILE):
        print(f"Sound file missing: {SOUND_FILE}")
        return

    unique_alias = f"alert_sound_{time.time_ns()}"
    windll.winmm.mciSendStringW(f'open "{SOUND_FILE}" type waveaudio alias {unique_alias}', None, 0, None)
    windll.winmm.mciSendStringW(f"play {unique_alias}", None, 0, None)
    time.sleep(1)
    windll.winmm.mciSendStringW(f"close {unique_alias}", None, 0, None)


def capture_window(hwnd):
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width = right - left
    height = bottom - top

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()

    save_bitmap = win32ui.CreateBitmap()
    save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
    save_dc.SelectObject(save_bitmap)

    windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)

    bmpinfo = save_bitmap.GetInfo()
    bmpstr = save_bitmap.GetBitmapBits(True)
    img = np.frombuffer(bmpstr, dtype="uint8")
    img.shape = (bmpinfo["bmHeight"], bmpinfo["bmWidth"], 4)

    win32gui.DeleteObject(save_bitmap.GetHandle())
    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)

    return img


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
                template = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
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
        min_h = max(12, int(roi_h * 0.18))
        max_h = max(min_h, int(roi_h * 0.65))
        max_w = max(8, int(roi_w * 0.25))
        min_y = int(roi_h * 0.35)

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
        boxes = []
        for label in range(1, num_labels):
            x, y, w, h, area = stats[label]
            if y >= min_y and min_h <= h <= max_h and 2 <= w <= max_w and area >= 20:
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

    def record_stopped(self, result, now):
        if not self.enabled:
            return
        if self.state == self.RECORDING:
            self.state = self.COOLDOWN
            self.cooldown_until = now + self.config["cooldown_sec"]
            self.last_grade = result["grade"] if result else None
            self.start_hits = 0
            self.end_hits = 0

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
        self.outside_frames = 0
        self.beep_count = 0
        self.max_outside_s = 0.0
        self.current_outside_started_at = None

    def add_frame(self, is_outside, white_point, rectangle, beep_event):
        current_time = (datetime.now() - self.start_time).total_seconds()
        x, y, w, h = rectangle

        self.total_frames += 1
        if is_outside:
            self.outside_frames += 1

        if beep_event:
            self.beep_count += 1

        if is_outside and self.current_outside_started_at is None:
            self.current_outside_started_at = current_time
        elif not is_outside and self.current_outside_started_at is not None:
            self.max_outside_s = max(self.max_outside_s, current_time - self.current_outside_started_at)
            self.current_outside_started_at = None

        if white_point:
            self.data.append([current_time, is_outside, white_point[0], white_point[1], w, h])
        else:
            self.data.append([current_time, is_outside, None, None, w, h])

    def finish(self):
        duration_s = (datetime.now() - self.start_time).total_seconds()
        if self.current_outside_started_at is not None:
            self.max_outside_s = max(self.max_outside_s, duration_s - self.current_outside_started_at)
            self.current_outside_started_at = None

        outside_ratio = self.outside_frames / self.total_frames if self.total_frames else 0.0
        good_max = self.config["grading"]["good_max"]
        soso_max = self.config["grading"]["soso_max"]
        if outside_ratio <= good_max:
            grade = "GOOD"
        elif outside_ratio <= soso_max:
            grade = "SOSO"
        else:
            grade = "BAD"

        return {
            "timestamp": self.timestamp,
            "duration_s": duration_s,
            "total_frames": self.total_frames,
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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(folder_name, f"record_{timestamp}.csv")

    rect_w = rectangle[2] if rectangle else 0
    rect_h = rectangle[3] if rectangle else 0
    with open(filename, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Rectangle Size", f"{rect_w}x{rect_h}"])
        writer.writerow(["Time (s)", "Is Outside", "X", "Y", "Rectangle Width", "Rectangle Height"])
        writer.writerows(data)
    print(f"Record saved to {filename}")
    return filename


def append_session_summary(result):
    filename = os.path.join(record_folder(), "sessions.csv")
    write_header = not os.path.exists(filename) or os.path.getsize(filename) == 0
    header = [
        "timestamp",
        "duration_s",
        "total_frames",
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
        result["outside_frames"],
        f"{result['outside_ratio']:.6f}",
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
    if cv2.imwrite(filename, roi):
        return filename
    return None


def draw_result_card(frame, result):
    if result is None:
        return

    grade = result["grade"]
    ratio_text = f"{result['outside_ratio'] * 100:.1f}%"
    title = f"{grade} - outside {ratio_text} ({result['outside_frames']}/{result['total_frames']} frames)"
    subtitle = f"beeps {result['beep_count']} | max outside {result['max_outside_s']:.2f}s"

    grade_colors = {
        "GOOD": (40, 180, 90),
        "SOSO": (0, 190, 230),
        "BAD": (40, 80, 230),
    }
    color = grade_colors.get(grade, (255, 255, 255))

    height, width = frame.shape[:2]
    card_w = min(width - 40, 680)
    card_h = 120
    x1 = max(20, (width - card_w) // 2)
    y1 = 30
    x2 = x1 + card_w
    y2 = y1 + card_h

    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (25, 25, 25), -1)
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 3)
    cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)
    cv2.putText(frame, title, (x1 + 22, y1 + 48), cv2.FONT_HERSHEY_SIMPLEX, 0.85, color, 2)
    cv2.putText(frame, subtitle, (x1 + 22, y1 + 88), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (235, 235, 235), 2)


def draw_hud(frame, circle_radius, session, is_muted, auto_label, timer_seconds, timer_method, status_message):
    cv2.putText(frame, f"Circle Radius: {circle_radius}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    if session is not None:
        elapsed_time = (datetime.now() - session.start_time).total_seconds()
        minutes, seconds = divmod(int(elapsed_time), 60)
        time_str = f"{minutes:02d}:{seconds:02d}"
        cv2.putText(
            frame,
            f"Recording: Yes ({time_str}, {session.source})",
            (10, 70),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 255),
            2,
        )
    else:
        cv2.putText(frame, "Recording: No", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    mute_color = (0, 0, 255) if is_muted else (255, 255, 255)
    cv2.putText(frame, f"Muted: {'Yes' if is_muted else 'No'}", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, mute_color, 2)
    cv2.putText(frame, auto_label, (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (180, 230, 255), 2)

    timer_text = "Timer: --"
    if timer_seconds is not None:
        timer_text = f"Timer: 00:{timer_seconds:02d}"
        if timer_method:
            timer_text += f" ({timer_method})"
    cv2.putText(frame, timer_text, (10, 185), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (220, 220, 220), 2)

    if status_message:
        cv2.putText(frame, status_message, (10, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 220, 255), 2)


def set_status(message):
    return message, time.time() + STATUS_OVERLAY_SEC


def main(window_title, config):
    windows = gw.getWindowsWithTitle(window_title)
    if not windows:
        print(f"Window not found: {window_title}")
        return

    hwnd = win32gui.FindWindow(None, window_title)
    if not hwnd:
        print(f"Window handle not found: {window_title}")
        return

    initial_rectangle = None
    session = None
    is_muted = False
    was_outside = False
    circle_radius = config["detect"]["circle_radius"]

    timer_detector = TimerDetector(config)
    auto_state = AutoStateMachine(config)
    last_result = None
    result_overlay_until = 0.0
    status_message = ""
    status_message_until = 0.0

    while True:
        now = time.time()
        screenshot = capture_window(hwnd)
        raw_frame = cv2.cvtColor(screenshot, cv2.COLOR_RGBA2BGR)
        frame = raw_frame.copy()
        timer_seconds = None
        timer_method = None

        if initial_rectangle is None:
            initial_rectangle, frame = detect_black_rectangle(frame)
        elif initial_rectangle:
            x, y, w, h = initial_rectangle
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        if initial_rectangle:
            timer_seconds, timer_roi_rect, timer_method = timer_detector.read_seconds(raw_frame, initial_rectangle, now)
            if timer_roi_rect:
                rx, ry, rw, rh = timer_roi_rect
                cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (255, 180, 0), 1)

            if auto_state.maybe_start(timer_seconds, now, session is not None):
                session = SessionRecorder(config, "auto")
                status_message, status_message_until = set_status("Auto recording started")

            circle_center = draw_circle(frame, initial_rectangle, circle_radius)
            is_outside, white_point = check_white_point_outside_circle(
                raw_frame, initial_rectangle, circle_center, circle_radius
            )

            beep_event = is_outside and not was_outside
            if beep_event:
                threading.Thread(target=play_alert_sound, args=(is_muted,)).start()
                print("Outside detected")
            was_outside = is_outside

            if session is not None:
                session.add_frame(is_outside, white_point, initial_rectangle, beep_event)

            finish_reason = auto_state.maybe_finish(
                timer_seconds,
                now,
                session is not None,
                session.source if session is not None else None,
            )
            if finish_reason and session is not None:
                last_result = finish_recording(session, initial_rectangle)
                result_overlay_until = time.time() + RESULT_OVERLAY_SEC
                status_message, status_message_until = set_status(f"Auto recording stopped: {finish_reason}")
                session = None
                auto_state.record_stopped(last_result, time.time())

        if now >= status_message_until:
            status_message = ""

        draw_hud(
            frame,
            circle_radius,
            session,
            is_muted,
            auto_state.label(session),
            timer_seconds,
            timer_method,
            status_message,
        )

        if time.time() < result_overlay_until:
            draw_result_card(frame, last_result)

        cv2.imshow("Display", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            if session is not None:
                last_result = finish_recording(session, initial_rectangle)
                auto_state.record_stopped(last_result, time.time())
                session = None
            break
        if key in (ord("+"), ord("=")):
            circle_radius += 1
            config["detect"]["circle_radius"] = circle_radius
            save_config(config)
            status_message, status_message_until = set_status(f"Circle radius: {circle_radius}")
        elif key in (ord("-"), ord("_")):
            circle_radius = max(1, circle_radius - 1)
            config["detect"]["circle_radius"] = circle_radius
            save_config(config)
            status_message, status_message_until = set_status(f"Circle radius: {circle_radius}")
        elif key == ord("r"):
            if session is None:
                session = SessionRecorder(config, "manual")
                status_message, status_message_until = set_status("Manual recording started")
            else:
                last_result = finish_recording(session, initial_rectangle)
                result_overlay_until = time.time() + RESULT_OVERLAY_SEC
                if session.source == "auto":
                    auto_state.record_stopped(last_result, time.time())
                session = None
                status_message, status_message_until = set_status("Recording stopped")
        elif key == ord("m"):
            is_muted = not is_muted
            status_message, status_message_until = set_status(f"Mute {'enabled' if is_muted else 'disabled'}")
            print(f"Mute {'enabled' if is_muted else 'disabled'}")
        elif key == ord("c"):
            if initial_rectangle:
                saved_path = save_timer_calibration(raw_frame, initial_rectangle, timer_detector)
                if saved_path:
                    status_message, status_message_until = set_status(f"Saved timer ROI: {os.path.basename(saved_path)}")
                    print(f"Saved timer ROI to {saved_path}")
                else:
                    status_message, status_message_until = set_status("Failed to save timer ROI")
            else:
                status_message, status_message_until = set_status("No play rectangle yet")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        hide_console()
    loaded_config, loaded_warnings = load_config()
    app = App(loaded_config, loaded_warnings)
    app.mainloop()
