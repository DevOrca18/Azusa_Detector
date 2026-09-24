"""Delta feedback and compact controls for the live measurement guide."""
import math
import tkinter as tk
from tkinter import ttk

from ui_theme import PALETTE, ToggleSwitch, SectionCard
from localization import t


DEFAULT_DELTA = {
    "enabled": False, "guide_enabled": False, "method": "axes", "x_px": 50.0, "y_px": 50.0,
    "distance_px": 10.0, "preview_width": 640, "preview_height": 360,
    "preview_source": "preset",
}

PREVIEW_PRESETS = {
    "16:9 기본 · 640 × 360": (640, 360),
    "HD · 1280 × 720": (1280, 720),
    "FHD · 1920 × 1080": (1920, 1080),
    "QHD · 2560 × 1440": (2560, 1440),
    "4K · 3840 × 2160": (3840, 2160),
}
CUSTOM_PREVIEW = "커스텀 · 직접 입력"
OBS_PREVIEW = "OBS 감지 영역"


def delta_exceeded(delta, config):
    if not config["enabled"] or delta is None:
        return None
    dx, dy = delta
    if config["method"] == "distance":
        return math.hypot(dx, dy) >= config["distance_px"]
    return abs(dx) >= config["x_px"] or abs(dy) >= config["y_px"]


def threshold_label(config):
    if not config["enabled"]:
        return "Delta feedback OFF"
    if config["method"] == "distance":
        return f"Delta distance >= {config['distance_px']:g} px"
    return f"|dX| >= {config['x_px']:g} OR |dY| >= {config['y_px']:g} px"


class DeltaFeedback:
    def __init__(self, config):
        self.config = config.copy()
        self.over_threshold = None
        self.last_event_at = -math.inf
        self.last_alert_delta = None

    def update(self, delta, detected, now):
        self.over_threshold = delta_exceeded(delta if detected else None, self.config)
        # At most one sound per second; every over-threshold sample is still logged.
        event = self.over_threshold is True and now - self.last_event_at >= 1.0
        if event:
            self.last_event_at = now
            self.last_alert_delta = delta
        return event

    def visible(self, now):
        return self.config["enabled"] and now - self.last_event_at < 0.8


def preview_transform(canvas_width, canvas_height, source_width, source_height):
    scale = min(max(1, canvas_width - 32) / source_width, max(1, canvas_height - 32) / source_height)
    return (canvas_width - source_width * scale) / 2, (canvas_height - source_height * scale) / 2, scale


class DeltaSettings:
    def __init__(self, parent, config):
        self.saved_config = config.copy()
        self.mode = "position"
        self.enabled = tk.BooleanVar(value=config["enabled"])
        self.guide_enabled = tk.BooleanVar(value=config.get("guide_enabled", False))
        self.method = tk.StringVar(value=config["method"])
        self.x_px = tk.StringVar(value=str(config["x_px"]))
        self.y_px = tk.StringVar(value=str(config["y_px"]))
        self.distance_px = tk.StringVar(value=str(config["distance_px"]))

        self.controls = SectionCard(parent, t("이동량 경고"), "03")
        controls = self.controls.content
        controls.columnconfigure((0, 1), weight=1, uniform="delta_inputs")
        for column, (label, variable, attr) in enumerate((("비프음", self.enabled, "toggle"),
                                                        ("측정 가이드", self.guide_enabled, "guide_toggle"))):
            group = ttk.Frame(controls, style="Card.TFrame")
            group.grid(row=0, column=column, sticky="ew", pady=(0, 12),
                       padx=(0, 10) if column == 0 else (10, 0))
            ttk.Label(group, text=t(label), style="Section.TLabel").pack(side="left")
            toggle = ToggleSwitch(group, variable, compact=True)
            toggle.pack(side="right", padx=(6, 0))
            setattr(self, attr, toggle)
        ttk.Radiobutton(controls, text=t("X · Y 개별"), variable=self.method, value="axes",
                        style="Mode.TRadiobutton").grid(row=1, column=0, sticky="ew", padx=(0, 5))
        ttk.Radiobutton(controls, text=t("합산 거리"), variable=self.method, value="distance",
                        style="Mode.TRadiobutton").grid(row=1, column=1, sticky="ew", padx=(5, 0))
        self.axes_fields = ttk.Frame(controls, style="Card.TFrame")
        self.distance_fields = ttk.Frame(controls, style="Card.TFrame")
        for fields in (self.axes_fields, self.distance_fields):
            fields.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        ttk.Label(self.axes_fields, text="X").pack(side="left", padx=(0, 8))
        self.x_entry = ttk.Entry(self.axes_fields, textvariable=self.x_px, width=8)
        self.x_entry.pack(side="left", padx=(0, 24))
        ttk.Label(self.axes_fields, text="Y").pack(side="left", padx=(0, 8))
        self.y_entry = ttk.Entry(self.axes_fields, textvariable=self.y_px, width=8)
        self.y_entry.pack(side="left")
        self.distance_entry = ttk.Entry(self.distance_fields, textvariable=self.distance_px, width=12)
        self.distance_entry.pack(side="left", padx=(0, 8))
        ttk.Label(self.distance_fields, text="px").pack(side="left")
        self.method_trace = self.method.trace_add("write", self.redraw)
        self.redraw()

    def dispose(self):
        if self.method_trace:
            self.method.trace_remove("write", self.method_trace)
            self.method_trace = None

    def set_mode(self, mode):
        self.mode = mode

    def export(self):
        # Retain legacy dimensions for config compatibility; no sample is rendered.
        return {**self.saved_config, "enabled": self.enabled.get(), "guide_enabled": self.guide_enabled.get(),
                "method": self.method.get(), "x_px": self.x_px.get(), "y_px": self.y_px.get(),
                "distance_px": self.distance_px.get()}

    def redraw(self, *_):
        axes = self.method.get() == "axes"
        (self.axes_fields if axes else self.distance_fields).grid()
        (self.distance_fields if axes else self.axes_fields).grid_remove()
