"""Presentation of setup, separate from capture and monitoring behavior."""
import tkinter as tk
import sys
from tkinter import ttk

from delta_feedback import DeltaSettings
from ui_theme import BrandRail, ScrollableSettings, SectionCard, ToggleSwitch
from localization import LANGUAGES, t
from live_preview import LivePreview


def build_setup(app, config, resource_path, circle_judge):
    app.columnconfigure(1, weight=1)
    app.rowconfigure(0, weight=1)
    app.brand_rail = BrandRail(app, resource_path("assets/ui/azusa-portrait-v1.png"), app.open_records, app.activity)
    app.brand_rail.grid(row=0, column=0, sticky="ns")
    body = ttk.Frame(app, style="App.TFrame", padding=(20, 18, 20, 14))
    app.body = body
    body.grid(row=0, column=1, sticky="nsew")
    body.columnconfigure(0, weight=0, minsize=360)
    body.columnconfigure(1, weight=1)
    body.rowconfigure(1, weight=1)
    header = ttk.Frame(body, style="App.TFrame")
    header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text="MONITORING STUDIO", style="Eyebrow.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(header, text="Azusa Detector", style="Title.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 5))
    ttk.Label(header, textvariable=app.phase_var, style="Badge.TLabel").grid(row=1, column=1, sticky="e")
    app.settings_toggle = ttk.Button(header, text="‹  " + t("설정 접기"), command=app.toggle_settings, style="Gold.TButton")
    app.settings_toggle.grid(row=2, column=0, sticky="w", pady=(12, 0))
    app.settings_visible = True

    language = ttk.Frame(header, style="App.TFrame")
    language.grid(row=2, column=1, sticky="e")
    ttk.Label(language, text="Language", style="Subtitle.TLabel").pack(side="left", padx=(0, 8))
    app.language_combo = ttk.Combobox(language, state="readonly", textvariable=app.language_var,
                                      values=tuple(LANGUAGES.values()), width=11)
    app.language_combo.pack(side="left")
    app.language_combo.bind("<<ComboboxSelected>>", app.change_language)

    app.left_scroller = ScrollableSettings(body)
    app.left_scroller.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
    form = app.left_scroller.inner
    app.main_frame = form

    app.window_section = SectionCard(form, t("연결할 창"), "01")
    app.window_section.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    windows = app.window_section.content
    windows.columnconfigure(1, weight=1)
    app.required_labels = {}
    for index, (key, label, variable) in enumerate((("obs", "OBS 화면", app.obs_window_var), ("game", "게임 창", app.game_window_var))):
        row = index * 2
        ttk.Label(windows, text=t(label), style="Section.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=(0, 10))
        combo = ttk.Combobox(windows, textvariable=variable, state="readonly", width=24)
        combo.grid(row=row, column=1, sticky="ew", pady=(0, 10))
        setattr(app, key + "_window_combo", combo)
        error = ttk.Label(windows, style="Error.TLabel")
        error.grid(row=row + 1, column=1, sticky="w", pady=(0, 8))
        app.required_labels[key] = error
    app.refresh_button = ttk.Button(windows, text=t("창 목록 새로고침") + "   F5", command=app.refresh_windows)
    app.refresh_button.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(2, 0))
    app.refresh_windows(update_status=False)

    app.mode_section = SectionCard(form, t("모니터링 방식"), "02")
    app.mode_section.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    modes = app.mode_section.content
    modes.columnconfigure((0, 1), weight=1, uniform="modes")
    app.mode_controls = []
    for index, (label, value) in enumerate((("↗  " + t("위치 추적"), "position"), ("◎  " + t("원형 판정"), "circle"))):
        control = ttk.Radiobutton(modes, text=label, value=value, variable=app.monitor_mode_var, command=app.update_mode_controls, style="Mode.TRadiobutton")
        control.grid(row=0, column=index, sticky="ew", padx=(0, 5) if index == 0 else (5, 0))
        app.mode_controls.append(control)

    app.detect_section = SectionCard(form, t("원형 판정 기준"), "03")
    app.detect_section.grid(row=2, column=0, sticky="ew", pady=(0, 10))
    detect = app.detect_section.content
    detect.columnconfigure(1, weight=1)
    beep_row = ttk.Frame(detect, style="Card.TFrame")
    beep_row.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 12))
    ttk.Label(beep_row, text=t("비프음"), style="Section.TLabel").pack(side="left")
    app.circle_beep_toggle = ToggleSwitch(beep_row, app.circle_beep_var)
    app.circle_beep_toggle.pack(side="right")
    ttk.Label(detect, text=t("원 반지름"), style="Section.TLabel").grid(row=1, column=0, padx=(0, 12))
    radius = ttk.Entry(detect, textvariable=app.radius_var, width=7, justify="center")
    app.radius_entry = radius
    radius.grid(row=1, column=1, sticky="ew")
    ttk.Label(detect, text="px", style="Hint.TLabel").grid(row=1, column=2, padx=8)
    minus = ttk.Button(detect, text="−", command=app.decrease_radius, width=2)
    minus.grid(row=1, column=3, padx=(0, 5))
    plus = ttk.Button(detect, text="+", command=app.increase_radius, width=2)
    plus.grid(row=1, column=4)
    app.circle_controls.extend((radius, minus, plus))
    app.grading_section = ttk.Frame(detect, style="Card.TFrame")
    app.grading_section.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(14, 0))
    app.grading_entries = []
    for index, (label, variable) in enumerate((("GOOD ≤", app.good_var), ("SOSO ≤", app.soso_var))):
        ttk.Label(app.grading_section, text=label, style="Section.TLabel").grid(row=0, column=index * 2, padx=(0 if index == 0 else 16, 8))
        entry = ttk.Entry(app.grading_section, textvariable=variable, width=6, justify="center")
        entry.grid(row=0, column=index * 2 + 1, sticky="w")
        app.circle_controls.append(entry)
        app.grading_entries.append(entry)
    ttk.Label(app.grading_section, text=t("원 밖 감지 비율 · 0.05 = 5%"), style="Hint.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(10, 0))

    app.delta_settings = DeltaSettings(form, config["delta_feedback"])
    app.live_preview = LivePreview(body, app, sys.modules[circle_judge.__module__])
    app.live_preview.grid(row=1, column=1, sticky="nsew")
    app.delta_settings.controls.grid(row=2, column=0, sticky="ew", pady=(0, 10))
    app.input_error_var = tk.StringVar()
    app.input_error_label = ttk.Label(form, textvariable=app.input_error_var, style="Error.TLabel")
    app.input_error_label.grid(row=4, column=0, sticky="ew", pady=(8, 0))

    app.record_section = SectionCard(form, t("기록"), "04")
    app.record_section.grid(row=3, column=0, sticky="ew")
    auto = app.record_section.content
    ttk.Checkbutton(auto, text=t("게임 타이머로 자동 기록"), variable=app.auto_enabled_var).grid(row=0, column=0, sticky="w")
    cfg = config["auto"]
    ttk.Label(auto, text=t("{a}–{b}초 시작 · {c}–{d}초 종료", a=cfg["start_band"][0], b=cfg["start_band"][1], c=cfg["end_band"][0], d=cfg["end_band"][1]), style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))

    footer = ttk.Frame(body, style="App.TFrame")
    footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
    footer.columnconfigure(0, weight=1)
    ttk.Label(footer, textvariable=app.status_var, style="Status.TLabel", wraplength=530).grid(row=0, column=0, sticky="w")
    app.start_button = ttk.Button(footer, text=t("모니터링 시작") + "   →", command=app.start_monitoring, style="Primary.TButton")
    app.start_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(20, 0))
    app.connection_traces = [(variable, variable.trace_add("write", app.settings_changed))
                             for variable in (app.obs_window_var, app.game_window_var, app.monitor_mode_var, app.radius_var,
                                              app.good_var, app.soso_var, app.circle_beep_var, app.delta_settings.enabled,
                                              app.delta_settings.guide_enabled, app.delta_settings.method,
                                              app.delta_settings.x_px, app.delta_settings.y_px, app.delta_settings.distance_px,
                                              app.auto_enabled_var)]
    app.update_connection_status()

    app.bind("<F5>", app.handle_refresh_shortcut)
    app.bind("<Control-r>", app.handle_refresh_shortcut)
    app.bind("<Control-R>", app.handle_refresh_shortcut)
    app.bind("<KeyPress>", app.monitor_shortcut)
    if app.config_warnings:
        app.after(250, app.show_config_warnings)
    app.update_mode_controls()
    app.last_source_available = None
    app.check_preview_source()
