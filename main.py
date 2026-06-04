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
DISPLAY_WINDOW_NAME = "Display"
DISPLAY_MAX_WIDTH = 1280
DISPLAY_MAX_HEIGHT = 820

if getattr(sys, "frozen", False):
    APP_BASE_DIR = os.path.dirname(sys.executable)
else:
    APP_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def hide_console():
    try:
        console_window = win32gui.GetForegroundWindow()
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
        super().__init__(theme="equilux")

        self.config_data = config
        self.config_warnings = config_warnings

        self.title("Azusa Detector")
        self.geometry("480x460")
        self.minsize(460, 450)
        self.resizable(True, True)

        self.configure(background="#20242b")
        self.style = ttk.Style(self)
        self.configure_styles()

        self.window_var = tk.StringVar()
        self.radius_var = tk.StringVar(value=str(config["detect"]["circle_radius"]))
        self.good_var = tk.StringVar(value=str(config["grading"]["good_max"]))
        self.soso_var = tk.StringVar(value=str(config["grading"]["soso_max"]))
        self.auto_enabled_var = tk.BooleanVar(value=config["auto"]["enabled"])
        self.status_var = tk.StringVar(value="Ready")

        main_frame = ttk.Frame(self, padding=(18, 16, 18, 14), style="App.TFrame")
        main_frame.grid(row=0, column=0, sticky=tk.NSEW)
        main_frame.columnconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        ttk.Label(main_frame, text="Azusa Detector", style="Title.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 14)
        )

        window_section = ttk.LabelFrame(main_frame, text="Window", style="Section.TLabelframe")
        window_section.grid(row=1, column=0, sticky=tk.EW)
        window_section.columnconfigure(0, weight=1)
        self.window_combo = ttk.Combobox(window_section, textvariable=self.window_var, state="readonly")
        self.window_combo.grid(row=0, column=0, sticky=tk.EW, padx=(12, 8), pady=12)
        ttk.Button(window_section, text="Refresh", command=self.refresh_windows, width=10).grid(
            row=0, column=1, sticky=tk.E, padx=(0, 12), pady=12
        )
        self.refresh_windows(update_status=False)

        detect_section = ttk.LabelFrame(main_frame, text="Detection", style="Section.TLabelframe")
        detect_section.grid(row=2, column=0, sticky=tk.EW, pady=(12, 0))
        detect_section.columnconfigure(1, weight=1)
        ttk.Label(detect_section, text="Circle radius", style="Section.TLabel").grid(
            row=0, column=0, sticky=tk.W, padx=(12, 10), pady=12
        )
        ttk.Entry(detect_section, textvariable=self.radius_var, width=8, justify=tk.CENTER).grid(
            row=0, column=1, sticky=tk.W, pady=12
        )
        ttk.Button(detect_section, text="-", command=self.decrease_radius, width=3).grid(
            row=0, column=2, padx=(8, 4), pady=12
        )
        ttk.Button(detect_section, text="+", command=self.increase_radius, width=3).grid(
            row=0, column=3, padx=(0, 12), pady=12
        )

        grading_section = ttk.LabelFrame(main_frame, text="Grading", style="Section.TLabelframe")
        grading_section.grid(row=3, column=0, sticky=tk.EW, pady=(12, 0))
        grading_section.columnconfigure(1, weight=1)
        grading_section.columnconfigure(3, weight=1)
        ttk.Label(grading_section, text="GOOD max", style="Section.TLabel").grid(
            row=0, column=0, sticky=tk.W, padx=(12, 8), pady=12
        )
        ttk.Entry(grading_section, textvariable=self.good_var, width=10, justify=tk.CENTER).grid(
            row=0, column=1, sticky=tk.W, pady=12
        )
        ttk.Label(grading_section, text="SOSO max", style="Section.TLabel").grid(
            row=0, column=2, sticky=tk.W, padx=(18, 8), pady=12
        )
        ttk.Entry(grading_section, textvariable=self.soso_var, width=10, justify=tk.CENTER).grid(
            row=0, column=3, sticky=tk.W, padx=(0, 12), pady=12
        )

        auto_section = ttk.LabelFrame(main_frame, text="Auto Timer", style="Section.TLabelframe")
        auto_section.grid(row=4, column=0, sticky=tk.EW, pady=(12, 0))
        ttk.Checkbutton(auto_section, text="Enable auto start/finish", variable=self.auto_enabled_var).grid(
            row=0, column=0, sticky=tk.W, padx=12, pady=(12, 4)
        )
        auto_cfg = config["auto"]
        auto_hint = (
            f"Starts at {auto_cfg['start_band'][0]}-{auto_cfg['start_band'][1]}s, "
            f"ends at {auto_cfg['end_band'][0]}-{auto_cfg['end_band'][1]}s or timer lost "
            f"({auto_cfg['grace_sec']:.0f}s). Bands: config.json"
        )
        ttk.Label(auto_section, text=auto_hint, style="Hint.TLabel").grid(
            row=1, column=0, sticky=tk.W, padx=12, pady=(0, 10)
        )

        ttk.Button(main_frame, text="Start Monitoring", command=self.start_monitoring, style="Primary.TButton").grid(
            row=5, column=0, sticky=tk.EW, pady=(16, 8), ipady=4
        )

        ttk.Label(main_frame, textvariable=self.status_var, style="Status.TLabel").grid(row=6, column=0, sticky=tk.W)

        self.bind("<F5>", self.handle_refresh_shortcut)
        self.bind("<Control-r>", self.handle_refresh_shortcut)
        self.bind("<Control-R>", self.handle_refresh_shortcut)

        if self.config_warnings:
            self.after(250, self.show_config_warnings)

    def configure_styles(self):
        bg = "#20242b"
        panel = "#292f38"
        panel_border = "#3a414d"
        text = "#e6eaf0"
        muted = "#aab3c2"
        accent = "#57c7ff"
        accent_active = "#74d2ff"
        field = "#171b21"

        self.option_add("*Font", ("Segoe UI", 10))
        self.option_add("*TCombobox*Listbox.background", field)
        self.option_add("*TCombobox*Listbox.foreground", text)
        self.option_add("*TCombobox*Listbox.selectBackground", "#2f6f95")
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        self.style.configure(".", font=("Segoe UI", 10), background=bg, foreground=text)
        self.style.configure("App.TFrame", background=bg)
        self.style.configure("TLabel", background=bg, foreground=text)
        self.style.configure("Section.TLabel", background=panel, foreground=text)
        self.style.configure("Title.TLabel", background=bg, foreground="#ffffff", font=("Segoe UI", 18, "bold"))
        self.style.configure("Status.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        self.style.configure("Hint.TLabel", background=panel, foreground=muted, font=("Segoe UI", 9))

        self.style.configure(
            "Section.TLabelframe",
            background=panel,
            bordercolor=panel_border,
            relief=tk.SOLID,
        )
        self.style.configure(
            "Section.TLabelframe.Label",
            background=bg,
            foreground=muted,
            font=("Segoe UI", 10, "bold"),
        )
        self.style.configure("TCheckbutton", background=panel, foreground=text)
        self.style.map("TCheckbutton", background=[("active", panel)], foreground=[("disabled", "#707782")])

        self.style.configure(
            "TEntry",
            fieldbackground=field,
            foreground=text,
            insertcolor=text,
            bordercolor=panel_border,
            lightcolor=panel_border,
            darkcolor=panel_border,
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=field,
            background=field,
            foreground=text,
            arrowcolor=muted,
            bordercolor=panel_border,
            lightcolor=panel_border,
            darkcolor=panel_border,
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", field), ("focus", field)],
            foreground=[("readonly", text)],
            selectbackground=[("readonly", field)],
            selectforeground=[("readonly", text)],
        )

        self.style.configure("TButton", background="#343b46", foreground=text, bordercolor="#444c59", padding=(10, 5))
        self.style.map(
            "TButton",
            background=[("active", "#3d4653"), ("pressed", "#2b313b")],
            foreground=[("disabled", "#777f8b")],
        )
        self.style.configure(
            "Primary.TButton",
            background=accent,
            foreground="#10151b",
            bordercolor=accent,
            font=("Segoe UI", 11, "bold"),
            padding=(12, 7),
        )
        self.style.map(
            "Primary.TButton",
            background=[("active", accent_active), ("pressed", "#40b7ee")],
            foreground=[("active", "#10151b"), ("pressed", "#10151b")],
        )

    def show_config_warnings(self):
        messagebox.showwarning("Azusa Detector config", "\n".join(self.config_warnings))

    def handle_refresh_shortcut(self, event=None):
        self.refresh_windows()
        return "break"

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
        # 직접 실행하지 않고 요청만 남김 — 모니터링 종료 후 시작창으로 복귀하는 루프(__main__)가 처리
        self.monitor_target = (window_title, validated_config)
        self.destroy()


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
    cv2.putText(frame, text, (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def text_width(text, scale=0.55, thickness=1):
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


def draw_shortcut_guide(frame, margin):
    height, width = frame.shape[:2]
    controls = [
        ("Q/ESC", "Back to setup"),
        ("R", "Record on/off"),
        ("M", "Mute"),
        ("+/-", "Radius"),
        ("C", "Save timer ROI"),
    ]

    bg = (18, 22, 28)
    border = (68, 80, 96)
    accent = (255, 199, 82)
    muted = (156, 168, 184)
    text = (232, 238, 244)
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
    ratio_text = f"{result['outside_ratio'] * 100:.1f}%"
    title = f"{grade}"
    detail = f"outside {ratio_text}  |  {result['outside_frames']}/{result['total_frames']} frames"
    extra = f"beeps {result['beep_count']}  |  max outside {result['max_outside_s']:.2f}s"

    grade_colors = {
        "GOOD": (92, 220, 126),
        "SOSO": (64, 202, 255),
        "BAD": (86, 118, 255),
    }
    accent = grade_colors.get(grade, (230, 230, 230))

    height, width = frame.shape[:2]
    margin = max(14, int(min(width, height) * 0.018))
    card_w = min(max(360, width // 2), width - margin * 2)
    card_h = 132
    x1 = max(margin, (width - card_w) // 2)
    y1 = margin
    x2 = x1 + card_w
    y2 = y1 + card_h

    draw_alpha_rect(frame, x1, y1, x2, y2, (18, 22, 28), 0.88)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (70, 82, 98), 1)
    cv2.rectangle(frame, (x1, y1), (x1 + 6, y2), accent, -1)
    draw_text(frame, title, x1 + 24, y1 + 45, 1.1, accent, 2)
    draw_text(frame, detail, x1 + 24, y1 + 78, 0.62, (238, 242, 246), 1)
    draw_text(frame, extra, x1 + 24, y1 + 108, 0.52, (170, 180, 192), 1)


def draw_hud(frame, circle_radius, session, is_muted, auto_label, timer_seconds, timer_method, status_message, last_result=None):
    height, width = frame.shape[:2]
    margin = max(12, int(min(width, height) * 0.014))
    panel_w = min(max(330, int(width * 0.28)), width - margin * 2)
    panel_h = 132 if not status_message else 158
    x1 = margin
    y1 = margin
    x2 = x1 + panel_w
    y2 = y1 + panel_h

    bg = (18, 22, 28)
    border = (68, 80, 96)
    text = (235, 240, 245)
    muted = (156, 168, 184)
    accent = (255, 199, 82)
    red = (72, 94, 232)
    green = (92, 210, 126)
    blue = (255, 176, 74)
    gray = (86, 94, 106)

    draw_alpha_rect(frame, x1, y1, x2, y2, bg, 0.78)
    cv2.rectangle(frame, (x1, y1), (x2, y2), border, 1)
    draw_text(frame, "AZUSA DETECTOR", x1 + 14, y1 + 24, 0.48, muted, 1)

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

    badge_y = y1 + 39
    next_x = draw_badge(frame, x1 + 14, badge_y, rec_text, rec_color)
    if next_x + 118 < x2:
        next_x = draw_badge(frame, next_x + 8, badge_y, auto_text, auto_color)
    if next_x + 94 < x2:
        draw_badge(frame, next_x + 8, badge_y, timer_text, (52, 62, 74))

    row_y = y1 + 92
    draw_text(frame, f"Radius {circle_radius}", x1 + 14, row_y, 0.52, text, 1)
    mute_label = "Muted ON" if is_muted else "Muted OFF"
    mute_color = (80, 96, 230) if is_muted else muted
    draw_text(frame, mute_label, x1 + 130, row_y, 0.52, mute_color, 1)
    if last_result is not None:
        # 결과 카드(3초)가 사라진 뒤에도 마지막 세션 결과를 항상 확인 가능
        grade_colors = {"GOOD": (92, 220, 126), "SOSO": (64, 202, 255), "BAD": (86, 118, 255)}
        last_text = f"Last {last_result['grade']} {last_result['outside_ratio'] * 100:.1f}%"
        draw_text(frame, last_text, x1 + 246, row_y, 0.52, grade_colors.get(last_result["grade"], muted), 1)

    if status_message:
        status_scale = fit_text_scale(status_message, panel_w - 28, 0.48, 0.36)
        draw_text(frame, status_message, x1 + 14, y1 + 125, status_scale, accent, 1)

    draw_shortcut_guide(frame, margin)


def set_status(message):
    return message, time.time() + STATUS_OVERLAY_SEC


def initialize_display_window(frame):
    cv2.namedWindow(DISPLAY_WINDOW_NAME, cv2.WINDOW_NORMAL)
    height, width = frame.shape[:2]
    scale = min(DISPLAY_MAX_WIDTH / width, DISPLAY_MAX_HEIGHT / height, 1.0)
    cv2.resizeWindow(DISPLAY_WINDOW_NAME, max(320, int(width * scale)), max(240, int(height * scale)))


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
    display_window_initialized = False

    while True:
        now = time.time()
        screenshot = capture_window(hwnd)
        raw_frame = cv2.cvtColor(screenshot, cv2.COLOR_RGBA2BGR)
        frame = raw_frame.copy()
        timer_seconds = None
        timer_method = None

        if initial_rectangle is None:
            initial_rectangle, frame = detect_black_rectangle(frame)
            if initial_rectangle is None:
                # 인식 전 무화면 방치 방지 — 뭘 기다리는지 표시 (매 프레임 갱신이라 인식되면 자연 소멸)
                status_message, status_message_until = set_status("Looking for play area (black box)...")
        elif initial_rectangle:
            x, y, w, h = initial_rectangle
            cv2.rectangle(frame, (x, y), (x + w, y + h), (88, 178, 118), 1)

        if initial_rectangle:
            timer_seconds, timer_roi_rect, timer_method = timer_detector.read_seconds(raw_frame, initial_rectangle, now)
            if timer_roi_rect:
                rx, ry, rw, rh = timer_roi_rect
                cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (255, 178, 74), 1)

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
            last_result,
        )

        if time.time() < result_overlay_until:
            draw_result_card(frame, last_result)

        if not display_window_initialized:
            initialize_display_window(frame)
            display_window_initialized = True

        cv2.imshow(DISPLAY_WINDOW_NAME, frame)

        key = cv2.waitKey(1) & 0xFF
        # 창 X버튼으로 닫아도 Q와 동일하게 안전 종료 (녹화 중이면 저장)
        window_closed = cv2.getWindowProperty(DISPLAY_WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1
        if key in (ord("q"), 27) or window_closed:  # Q / ESC / 창닫기
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
    # 모니터링 종료(Q/ESC/창닫기) 시 시작창으로 복귀 — 설정 바꾸려고 재실행할 필요 없음
    while True:
        loaded_config, loaded_warnings = load_config()
        app = App(loaded_config, loaded_warnings)
        app.mainloop()
        target = getattr(app, "monitor_target", None)
        if not target:
            break
        main(*target)
