"""One capture pipeline for silent preview and live monitoring, without UI state."""
import math
import time
from copy import deepcopy

from ui_theme import bgr


class MonitorEngine:
    def __init__(self, backend, config, activity=None):
        self.backend = backend
        self.activity = activity
        self.sound_error = None
        self.config = deepcopy(config)
        self.timer = backend.TimerDetector(self.config)
        self.auto = backend.AutoStateMachine(self.config)
        self.running = False
        self.muted = False
        self.session = None
        self.last_result = None
        self.timer_frame = None
        self.seconds = None
        self.reset()

    def reset(self):
        self._config_applied = False
        self.rectangle = None
        self.shape = None
        self.tracker = self.backend.PointTracker()
        self.feedback = self.backend.DeltaFeedback(self.config["delta_feedback"])
        self.was_outside = False
        self.outside = None
        self.guide_origin = None

    def configure(self, config):
        if self._config_applied and config == self.config:
            return
        # Threshold edits never reset the last valid coordinate.
        if not config["auto"]["enabled"] and self.session is not None and self.session.source == "auto":
            self.finish_session()
        self.config = deepcopy(config)
        self.timer.config = self.config
        self.auto.config = self.config["auto"]
        delta = deepcopy(self.config["delta_feedback"])
        if self.config["detect"]["circle_enabled"]:
            delta["enabled"] = False
        self.feedback.config = delta
        if self.session:
            self.session.config = self.config
        self._config_applied = True

    def log(self, key, level="info", **values):
        if self.activity is not None:
            self.activity.emit(key, level, **values)

    def start(self, config):
        self.configure(config)
        self.reset()
        self.configure(config)
        self.auto = self.backend.AutoStateMachine(self.config)
        self.running = True
        self.muted = False
        self.last_result = None

    def finish_session(self, now=None):
        if self.session is None:
            return
        # Clear only after successful persistence. Failed writes can be retried.
        result = self.backend.finish_recording(self.session, self.rectangle)
        self.auto.record_stopped(result, time.monotonic() if now is None else now)
        self.last_result = result
        self.session = None
        self.log("기록 저장 · {grade} · 감지 {n}프레임 · 경고 {beeps}회",
                 grade=result["grade"], n=result["detected_frames"], beeps=result["beep_count"])

    def stop(self):
        self.finish_session()
        self.running = False

    def record(self):
        if not self.running:
            return
        if self.session is None:
            self.session = self.backend.SessionRecorder(self.config, "manual")
            self.log("수동 기록 시작")
        else:
            self.finish_session()

    def missing(self, now):
        self.check_deadline(now)
        self.guide_origin = self.tracker.last_point
        self.timer_frame = None
        self.tracker.update(None, now)
        self.feedback.update(None, False, now)
        self.outside = None
        self.seconds = None
        if self.running and self.session is not None and self.rectangle:
            self.session.add_frame(None, None, self.rectangle, False, self.tracker,
                                   self.config["detect"]["circle_enabled"], None)
        # Fixed-duration runs keep recording through gaps and still expire on time.
        self.check_auto_finish(None, now)

    def check_auto_finish(self, seconds, now=None):
        if not self.running:
            return
        now = time.monotonic() if now is None else now
        reason = self.auto.maybe_finish(seconds, now, self.session is not None,
                                       self.session.source if self.session else None)
        if reason:
            self.finish_session(now)
            messages = {"duration elapsed": "자동 기록 종료 · 설정 시간 경과",
                        "timer end": "자동 기록 종료 · 종료 타이머 감지",
                        "timer lost": "자동 기록 종료 · 타이머 미감지"}
            self.log(messages[reason])

    def check_deadline(self, now):
        if self.auto.end_mode == "duration":
            self.check_auto_finish(None, now)

    def step(self, raw, game, now):
        app = self.backend
        self.check_deadline(now)
        if self.shape is not None and self.shape != raw.shape:
            # A resized source changes its coordinate system; save the old session first.
            self.finish_session()
            self.reset()
            self.configure(self.config)
        self.shape = raw.shape
        if self.rectangle is None:
            self.rectangle, _ = app.detect_black_rectangle(raw.copy())
        self.timer_frame = game
        self.seconds = None
        if game is not None:
            self.seconds, _, _ = self.timer.read_seconds(game, app.full_frame_rect(game), time.time())
        if self.running and self.rectangle and self.auto.maybe_start(self.seconds, now, self.session is not None):
            self.session = app.SessionRecorder(self.config, "auto")
            if self.auto.deadline is not None:
                self.log("자동 기록 시작 · {seconds}초", seconds=self.config["auto"]["duration_sec"])
            else:
                self.log("자동 기록 시작")
        point = app.detect_white_point(raw, self.rectangle) if self.rectangle else None
        # Capture the previous valid point before update; gaps never reset it.
        self.guide_origin = self.tracker.last_point or point
        self.tracker.update(point, now)
        delta_event = self.feedback.update(self.tracker.delta, self.tracker.detected, now)
        circle = self.config["detect"]["circle_enabled"]
        radius = self.config["detect"]["circle_radius"]
        self.outside = app.judge_circle(point, self.rectangle, radius, circle) if self.rectangle else None
        beep = (self.outside is True and not self.was_outside) or delta_event
        if self.running and beep and self.sound_enabled():
            try:
                if app.play_alert_sound(self.muted):
                    self.log("(ᓀ‸ᓂ)", "sound")
                self.sound_error = None
            except (OSError, RuntimeError) as error:
                if str(error) != self.sound_error:
                    self.log("오류: {error}", "error", error=str(error))
                self.sound_error = str(error)
        if self.outside is not None:
            self.was_outside = self.outside
        if self.running and self.session is not None and self.rectangle:
            self.session.add_frame(self.outside, point, self.rectangle, beep, self.tracker, circle, self.feedback.over_threshold)
        self.check_auto_finish(self.seconds, now)
        if self.rectangle is None:
            return None
        x, y, w, h = self.rectangle
        frame = raw[y:y + h, x:x + w].copy()
        if circle:
            app.draw_circle(frame, (0, 0, w, h), radius)
        if point is not None:
            center = (round(point[0] - x), round(point[1] - y))
            app.cv2.drawMarker(frame, center, bgr("warning") if self.alerting(now) else bgr("lilac"),
                               app.cv2.MARKER_CROSS, 12, 1)
        if self.alerting(now):
            app.cv2.rectangle(frame, (1, 1), (w - 2, h - 2), bgr("warning"), 2)
        return frame

    def alerting(self, now):
        return self.tracker.detected and (self.outside is True or self.feedback.visible(now))

    def sound_enabled(self):
        if self.config["detect"]["circle_enabled"]:
            return self.config["detect"].get("circle_beep_enabled", True)
        return self.config["delta_feedback"]["enabled"]

    def snapshot(self):
        now = time.monotonic()
        auto_recording = self.session is not None and self.session.source == "auto"
        elapsed = (self.backend.datetime.now() - self.session.start_time).total_seconds() if self.session else None
        if auto_recording and self.auto.started_at is not None:
            elapsed = max(0.0, now - self.auto.started_at)
        delta = self.tracker.delta
        return {"running": self.running, "recording": self.session is not None, "muted": self.muted,
                "sound_enabled": self.sound_enabled(), "can_calibrate": self.timer_frame is not None,
                "guide_origin": self.guide_origin, "guide": deepcopy(self.config["delta_feedback"]),
                "detected": self.tracker.detected, "relative": self.tracker.relative, "delta": delta,
                "distance": math.hypot(*delta) if delta else None, "gap": self.tracker.delta_seconds,
                "rectangle": self.rectangle, "alert": self.alerting(now),
                "circle": self.config["detect"]["circle_enabled"], "alert_delta": self.feedback.last_alert_delta,
                "seconds": self.seconds, "result": self.last_result,
                "remaining": self.auto.remaining(now) if auto_recording else None,
                "elapsed": elapsed}
