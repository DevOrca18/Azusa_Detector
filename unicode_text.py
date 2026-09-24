"""Cached Unicode labels for OpenCV's monitoring frame."""
import os
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from localization import get_language


@lru_cache(maxsize=64)
def font(size, language):
    names = {"ja": ("YuGothM.ttc", "malgun.ttf"), "zh": ("msyh.ttc", "malgun.ttf")}.get(language, ("malgun.ttf", "YuGothM.ttc"))
    for name in (*names, "arial.ttf"):
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=512)
def mask(text, size, language):
    face = font(size, language)
    left, top, right, bottom = face.getbbox(text)
    image = Image.new("L", (max(1, right - left), max(1, bottom - top)))
    ImageDraw.Draw(image).text((-left, -top), text, font=face, fill=255)
    return np.asarray(image)


def width(text, scale):
    return mask(text, max(10, round(scale * 32)), get_language()).shape[1]


def draw(frame, text, x, baseline, scale, color):
    alpha = mask(text, max(10, round(scale * 32)), get_language())
    x, y = int(x), int(baseline) - alpha.shape[0]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(frame.shape[1], x + alpha.shape[1]), min(frame.shape[0], y + alpha.shape[0])
    if x2 <= x1 or y2 <= y1:
        return
    coverage = alpha[y1-y:y2-y, x1-x:x2-x, None].astype(np.float32) / 255
    frame[y1:y2, x1:x2] = (frame[y1:y2, x1:x2] * (1 - coverage) + np.array(color) * coverage).astype(np.uint8)
