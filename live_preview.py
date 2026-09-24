"""Embedded preview/live dashboard; capture runs off Tk's UI thread."""
import queue
import math
import os
import win32process
import threading
import time
import tkinter as tk
from tkinter import ttk
from copy import deepcopy

from PIL import Image, ImageDraw, ImageTk
from action_button import ActionButton
from localization import t
from ui_theme import PALETTE
from monitor_engine import MonitorEngine
from sample_video import SampleVideo


class CaptureWorker:
    def __init__(self, backend, config, activity=None):
        self.backend = backend
        self.activity = activity
        self.last_error = None
        self.config = deepcopy(config)
        self.commands = queue.Queue()
        self.results = queue.Queue(maxsize=1)
        self.events = queue.Queue()
        self.lock = threading.Lock()
        self.preview_active = True
        self.sample_playing = False
        self.sample_player = SampleVideo(backend.resource_path("assets/samples/white-dot-loop.mp4"))
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def update(self, config, active):
        with self.lock:
            if config != self.config:
                self.config = deepcopy(config)
            self.preview_active = active

    def log(self, key, level="info", **values):
        if self.activity is not None:
            self.activity.emit(key, level, **values)

    def send(self, action, payload=None):
        self.commands.put((action, payload))

    def publish(self, frame, snapshot, error=None):
        try:
            self.results.get_nowait()
        except queue.Empty:
            pass
        snapshot = {**snapshot, "sample": self.sample_playing,
                    "sample_seconds": self.sample_player.position, "sample_duration": self.sample_player.duration}
        self.results.put_nowait((frame, snapshot, error))

    def capture(self, title, required=True):
        try:
            app = self.backend
            hwnd = app.win32gui.FindWindow(None, title) if title else 0
            if not hwnd or app.win32gui.IsIconic(hwnd):
                if required:
                    raise ValueError(t("OBS 창 선택" if not title else "OBS 창 없음 또는 최소화"))
                return None
            if win32process.GetWindowThreadProcessId(hwnd)[1] == os.getpid():
                raise ValueError(t("프로그램 자체 창은 캡처 불가"))
            return app.cv2.cvtColor(app.capture_window(hwnd), app.cv2.COLOR_BGRA2BGR)
        except Exception:
            if not required:
                return None
            raise


    def run(self):
        engine = MonitorEngine(self.backend, self.config, self.activity)
        source = None
        try:
            while True:
                started = time.monotonic()
                handling_command = False
                try:
                    with self.lock:
                        # Settings are replaced, never mutated; one snapshot is
                        # safe to reuse until the UI publishes a changed config.
                        config, active = self.config, self.preview_active
                    while not self.commands.empty():
                        action, payload = self.commands.get_nowait()
                        handling_command = True
                        if action == "start":
                            # A sample can never become a recorded monitoring source.
                            self.sample_player.close()
                            self.sample_playing = False
                            self.events.put(("sample", False))
                            engine.start(payload)
                            config = payload
                            source = ("window", config["windows"]["obs_title"])
                            self.events.put(("started", None))
                        elif action in ("stop", "close"):
                            engine.stop()
                            self.events.put(("closed" if action == "close" else "stopped", None))
                            if action == "close":
                                return
                        elif action == "sample" and not engine.running:
                            if payload:
                                self.sample_player.open()
                            else:
                                self.sample_player.close()
                            self.sample_playing = bool(payload)
                            engine.reset()
                            engine.configure(config)
                            source = None
                            self.events.put(("sample", self.sample_playing))
                        elif action == "record":
                            engine.record()
                        elif action == "mute" and engine.running:
                            engine.muted = not engine.muted
                            self.log("음소거 적용" if engine.muted else "음소거 해제")
                        elif action == "reset":
                            engine.finish_session()
                            engine.reset()
                            if self.sample_playing:
                                self.sample_player.restart()
                            self.log("다시 감지")
                        elif action == "calibrate" and engine.timer_frame is not None:
                            path = self.backend.save_timer_calibration(engine.timer_frame,
                                       self.backend.full_frame_rect(engine.timer_frame), engine.timer)
                            self.events.put(("saved", path))
                        handling_command = False
                    engine.configure(config)
                    engine.check_deadline(time.monotonic())
                    if not active and not engine.running and not self.sample_playing:
                        time.sleep(0.08)
                        continue
                    title = config["windows"]["obs_title"]
                    source_key = ("sample",) if self.sample_playing else ("window", title)
                    if source_key != source:
                        engine.finish_session()
                        engine.reset()
                        engine.configure(config)
                        source = source_key
                    if self.sample_playing:
                        raw, looped = self.sample_player.read(time.monotonic())
                        if looped:
                            engine.reset()
                            engine.configure(config)
                        game = None
                    else:
                        raw = self.capture(title)
                        game_title = config["windows"]["game_title"]
                        game = raw if game_title == title else self.capture(game_title, False)
                    frame = engine.step(raw, game, time.monotonic())
                    self.publish(frame, engine.snapshot())
                    if self.last_error is not None:
                        self.log("입력 연결 복구")
                        self.last_error = None
                except Exception as error:
                    if self.sample_playing or (handling_command and action == "sample"):
                        self.sample_player.close()
                        self.sample_playing = False
                        source = None
                        self.events.put(("sample", False))
                        engine.reset()
                        error = ValueError(t("샘플 영상 재생 실패"))
                    try:
                        engine.missing(time.monotonic())
                    except Exception:
                        pass
                    self.publish(None, engine.snapshot(), str(error))
                    if str(error) != self.last_error and not handling_command:
                        self.log("오류: {error}", "error", error=str(error))
                        self.last_error = str(error)
                    if handling_command:
                        self.events.put(("error", {"action": action, "message": str(error), "running": engine.running}))
                period = 1 / self.sample_player.fps if self.sample_playing else 0.035 if engine.running else 0.12
                time.sleep(max(0.005, period - (time.monotonic() - started)))
        finally:
            self.sample_player.close()


class LivePreview(ttk.Frame):
    def __init__(self, parent, app, backend):
        super().__init__(parent, style="Rounded.TFrame", padding=12)
        self.app, self.backend = app, backend
        # Language rebuilds retain raw entry strings; the worker only accepts
        # numeric, validated settings, even before its first UI update.
        self.worker = CaptureWorker(backend, backend.validate_config(app.config_data)[0], app.activity)
        self.active = True
        self.disposed = False
        self.frame = self.photo = None
        self.snapshot = {}
        self.sample_playing = False
        self.sample_pending = False
        self.calibration_saved_until = 0.0
        self.status = tk.StringVar(value=t("OBS 창 선택"))
        self.phase = tk.StringVar(value=t("미리보기"))
        self.metrics = {key: tk.StringVar(value="—") for key in ("position", "delta", "distance", "timer")}
        self.record_state = tk.StringVar(value=t("기록 대기"))
        self.last_result = tk.StringVar()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        toolbar = ttk.Frame(self, style="Card.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(toolbar, textvariable=self.phase, style="Metric.TLabel").pack(side="left")
        self.source_label = ttk.Label(toolbar, text=t("실제 화면"), style="Hint.TLabel")
        self.source_label.pack(side="right")
        metric_row = ttk.Frame(self, style="Card.TFrame")
        metric_row.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        for index, (key, label) in enumerate((("position", "좌표"), ("delta", "이동량"), ("distance", "합산 거리"), ("timer", "타이머"))):
            metric_row.columnconfigure(index, weight=1, uniform="metric")
            cell = ttk.Frame(metric_row, style="Metric.TFrame", padding=(9, 7))
            cell.grid(row=0, column=index, sticky="nsew", padx=(0, 6 if index < 3 else 0))
            ttk.Label(cell, text=t(label), style="MetricCaption.TLabel").pack(anchor="w")
            ttk.Label(cell, textvariable=self.metrics[key], style="MetricValue.TLabel").pack(anchor="w", pady=(7, 0))
        self.canvas = tk.Canvas(self, bg=PALETTE["deep"], width=440, height=260, highlightthickness=0)
        self.image_item = self.canvas.create_image(0, 0, state="hidden")
        self.empty_item = self.canvas.create_text(0, 0, fill=PALETTE["silver"], font=("Malgun Gothic", 10))
        self.canvas.grid(row=2, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", lambda event: self.paint())
        self.canvas.bind("<Button-1>", lambda event: self.canvas.focus_set())
        self.status_label = ttk.Label(self, textvariable=self.status, style="Metric.TLabel", wraplength=630)
        self.status_label.grid(row=3, column=0, sticky="w", pady=(12, 8))
        ttk.Separator(self).grid(row=4, column=0, sticky="ew", pady=(0, 10))
        controls = ttk.Frame(self, style="Card.TFrame")
        controls.grid(row=5, column=0, sticky="ew")
        self.actions = {}
        for action, key in (("record", "R"), ("mute", "M"), ("calibrate", "C"),
                            ("stop", "ESC"), ("reset", "D"), ("refresh", "F5"), ("sample", "S")):
            button = ActionButton(controls, key, lambda action=action: self.invoke_action(action))
            button.pack(side="left", padx=(0, 8))
            self.actions[action] = button
        self.record_button = self.actions["record"]
        self.mute_button = self.actions["mute"]
        self.reset_button = self.actions["reset"]
        ttk.Label(self, textvariable=self.record_state, style="Hint.TLabel").grid(row=6, column=0, sticky="w", pady=(10, 4))
        ttk.Label(self, textvariable=self.last_result, style="Hint.TLabel", wraplength=630).grid(row=7, column=0, sticky="w")
        self.update_actions()
        self.last_source_check = 0.0
        self.after_id = self.after(100, self.tick)

    def current_config(self):
        return self.app.read_settings()

    def invoke_action(self, action):
        self.update_actions()
        if self.actions[action].instate(["disabled"]):
            return
        if action == "stop":
            self.app.start_monitoring()
        elif action == "refresh":
            self.app.handle_refresh_shortcut()
        elif action == "sample":
            self.sample_pending = True
            self.worker.send("sample", not self.sample_playing)
            self.update_actions()
        else:
            self.worker.send(action)

    def update_actions(self):
        state = self.snapshot
        pending = self.app.monitor_pending
        running = self.app.monitor_running and not pending
        recording = state.get("recording", False)
        circle = self.app.monitor_mode_var.get() == "circle"
        sound_enabled = self.app.circle_beep_var.get() if circle else self.app.delta_settings.enabled.get()
        muted = state.get("muted", False) or not sound_enabled
        self.actions["record"].set_status("recording" if recording else "record",
            t("기록 종료" if recording else "기록 시작") + " · R", running, recording)
        self.actions["mute"].set_status("muted" if muted else "sound",
            t("비프음 설정 OFF" if not sound_enabled else "음소거 해제" if muted else "음소거") + " · M",
            running and sound_enabled, muted and sound_enabled)
        saved = time.monotonic() < self.calibration_saved_until
        self.actions["calibrate"].set_status("saved" if saved else "calibrate",
            t("타이머 영역 저장" if state.get("can_calibrate") else "게임 화면 없음") + " · C",
            running and state.get("can_calibrate", False), saved)
        self.actions["stop"].set_status("stop", t("모니터링 종료") + " · ESC", running)
        self.actions["reset"].set_status("detect", t("다시 감지") + " · D", not pending)
        self.actions["refresh"].set_status("refresh", t("창 목록 새로고침") + " · F5 / Ctrl+R",
            not self.app.monitor_running and not pending)
        self.actions["sample"].set_status("sample_stop" if self.sample_playing else "play",
            t("샘플 중지 · 실제 화면으로" if self.sample_playing else "샘플 영상 재생") + " · S",
            not self.app.monitor_running and not pending and not self.sample_pending, self.sample_playing)

    def tick(self):
        if self.disposed:
            return
        if time.monotonic() - self.last_source_check >= 1:
            self.app.check_preview_source()
            self.last_source_check = time.monotonic()
        try:
            config = self.current_config()
            self.worker.update(config, self.active)
            invalid = False
        except ValueError:
            invalid = True
        while not self.worker.events.empty():
            action, payload = self.worker.events.get_nowait()
            if action == "sample":
                if self.sample_playing != payload:
                    self.app.activity.emit("샘플 영상 재생" if payload else "샘플 중지 · 실제 화면으로")
                self.sample_pending = False
                self.sample_playing = payload
            else:
                self.app.monitor_event(action, payload)
            if self.disposed:
                return
        try:
            self.frame, self.snapshot, error = self.worker.results.get_nowait()
        except queue.Empty:
            pass
        else:
            state = self.snapshot
            self.phase.set("● " + t("모니터링 중") if state["running"] else "○ " + t("미리보기"))
            if state.get("sample"):
                self.phase.set("▷ " + t("샘플 영상 · 반복"))
                elapsed, duration = int(state["sample_seconds"]), int(state["sample_duration"])
                self.source_label.configure(text=f"{elapsed // 60:02d}:{elapsed % 60:02d} / {duration // 60:02d}:{duration % 60:02d} · 1920 × 1080")
            else:
                self.source_label.configure(text=t("실제 화면"))
            self.status.set(error or (t("검은 감지 영역 없음") if not state["rectangle"] else
                            t("원 이탈 · 경고" if state["circle"] else "경고 · 임계값 이상") if state["alert"] else
                            t("정상 감지") if state["detected"] else t("미감지 · 마지막 정상 좌표 유지")))
            self.status_label.configure(foreground=PALETTE["warning"] if state["alert"] or error else PALETTE["silver"])
            for key, value in (("position", state["relative"]), ("delta", state["delta"])):
                self.metrics[key].set("X  —\nY  —" if value is None else f"X {value[0]:+.1f}\nY {value[1]:+.1f}")
            self.metrics["distance"].set("— px" if state["distance"] is None else f"{state['distance']:.1f} px")
            self.metrics["timer"].set("— : —" if state["seconds"] is None else f"00:{state['seconds']:02d}")
            recording = state["recording"]
            if recording:
                minutes, seconds = divmod(int(state["elapsed"]), 60)
                elapsed = f"{minutes:02d}:{seconds:02d}"
                if state.get("remaining") is not None:
                    remaining_minutes, remaining_seconds = divmod(math.ceil(state["remaining"]), 60)
                    self.record_state.set("● " + t("자동 기록 {time} · 남은 {remaining}", time=elapsed,
                                                   remaining=f"{remaining_minutes:02d}:{remaining_seconds:02d}"))
                else:
                    self.record_state.set("● " + t("기록 중 {time}", time=elapsed))
            else:
                self.record_state.set(t("기록 대기") if state["running"] else t("미리보기 · 기록/소리 없음"))
            if state["result"]:
                result = state["result"]
                self.last_result.set(t("기록 저장 · {grade} · 감지 {n}프레임 · 경고 {beeps}회", grade=result["grade"], n=result["detected_frames"], beeps=result["beep_count"]))
            else:
                self.last_result.set("")
            self.paint()
        if invalid:
            self.status.set(t("입력값 확인 · 마지막 유효 설정 유지"))
        self.update_actions()
        self.app.brand_rail.log_view.append(self.app.activity.drain())
        self.after_id = self.after(60, self.tick)

    def paint(self):
        if self.disposed:
            return
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        if self.frame is None:
            self.canvas.itemconfigure(self.image_item, state="hidden")
            self.canvas.coords(self.empty_item, w / 2, h / 2)
            self.canvas.itemconfigure(self.empty_item, text=self.status.get(), width=max(100, w - 40), state="normal")
            return
        height, width = self.frame.shape[:2]
        ratio = min(w / width, h / height)
        size = (max(1, int(width * ratio)), max(1, int(height * ratio)))
        cv2 = self.backend.cv2
        small = cv2.resize(self.frame, size, interpolation=cv2.INTER_AREA if ratio < 1 else cv2.INTER_LINEAR)
        bitmap = Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        self.draw_guide(bitmap, width, height)
        self.photo = ImageTk.PhotoImage(bitmap, master=self.canvas)
        self.canvas.itemconfigure(self.empty_item, state="hidden")
        self.canvas.coords(self.image_item, w / 2, h / 2)
        self.canvas.itemconfigure(self.image_item, image=self.photo, state="normal")

    def draw_guide(self, bitmap, width, height):
        state = self.snapshot
        config = state.get("guide", {})
        if state.get("circle") or not config.get("guide_enabled"):
            return
        rectangle = state.get("rectangle")
        if rectangle is None:
            return
        origin = state.get("guide_origin")
        ox, oy = (origin[0] - rectangle[0], origin[1] - rectangle[1]) if origin else (width / 2, height / 2)
        sx, sy = bitmap.width / width, bitmap.height / height
        cx, cy = ox * sx, oy * sy
        draw = ImageDraw.Draw(bitmap, "RGBA")
        edge, ruler = (164, 135, 196, 230), (164, 135, 196, 100)
        if config["method"] == "axes":
            rx, ry = config["x_px"] * sx, config["y_px"] * sy
            draw.rectangle((cx - rx, cy - ry, cx + rx, cy + ry), outline=edge, width=2)
        else:
            rx, ry = config["distance_px"] * sx, config["distance_px"] * sy
            draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=edge, width=2)
        draw.line((cx - rx, cy, cx + rx, cy), fill=ruler, width=1)
        draw.line((cx, cy - ry, cx, cy + ry), fill=ruler, width=1)
        draw.line((cx - 3, cy, cx + 3, cy), fill=edge, width=1)
        draw.line((cx, cy - 3, cx, cy + 3), fill=edge, width=1)

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        self.after_cancel(self.after_id)
        self.worker.send("close")
