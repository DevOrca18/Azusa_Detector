"""Clock-paced looping video for the silent setup preview."""
import math
import time

import cv2


class SampleVideo:
    def __init__(self, path):
        self.path = path
        self.capture = None
        self.fps = 30.0
        self.count = 0
        self.duration = self.position = 0.0
        self.started = 0.0
        self.cycle = 0
        self.index = -1
        self.frame = None

    def open(self):
        self.close()
        capture = cv2.VideoCapture(self.path)
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if not capture.isOpened() or not math.isfinite(fps) or fps <= 0 or not math.isfinite(count) or count < 1:
            capture.release()
            raise OSError("Sample video unavailable")
        self.capture, self.fps, self.count = capture, fps, int(count)
        self.duration = self.count / self.fps
        self.restart()

    def restart(self):
        if self.capture is not None:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        self.started = time.monotonic()
        self.cycle = 0
        self.index = -1
        self.position = 0.0
        self.frame = None

    def read(self, now):
        if self.capture is None:
            raise OSError("Sample video unavailable")
        elapsed_frames = max(0, int((now - self.started) * self.fps))
        cycle, target = divmod(elapsed_frames, self.count)
        looped = cycle != self.cycle
        if not looped and target == self.index and self.frame is not None:
            return self.frame, False
        if looped:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self.cycle, self.index = cycle, -1
        # Skip decoding into RGB for frames that the wall clock has passed.
        while self.index < target:
            if not self.capture.grab():
                raise OSError("Sample video decode failed")
            self.index += 1
        ok, frame = self.capture.retrieve()
        if not ok or frame is None:
            raise OSError("Sample video decode failed")
        self.frame = frame
        self.position = target / self.fps
        return frame, looped

    def close(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        self.frame = None
