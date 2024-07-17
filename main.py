import tkinter as tk
from tkinter import ttk
import cv2
import numpy as np
import pygetwindow as gw
import mss
import threading
from ctypes import windll
import time
import os
import win32gui
import win32ui
import csv
from datetime import datetime

WHITE_THRESHOLD_LOW = np.array([0, 0, 200])
WHITE_THRESHOLD_HIGH = np.array([180, 25, 255])
SOUND_FILE = "alert.wav"
DEFAULT_RADIUS = 45

import tkinter as tk
from tkinter import ttk, font
import ttkthemes

class App(ttkthemes.ThemedTk):
    def __init__(self):
        super().__init__(theme="arc")

        self.title("Azusa Detector")
        self.geometry("400x350")

        self.style = ttk.Style(self)
        self.style.configure('TLabel', font=('Helvetica', 12))
        self.style.configure('TButton', font=('Helvetica', 12))

        self.window_var = tk.StringVar()
        self.radius_var = tk.StringVar(value=str(DEFAULT_RADIUS))

        main_frame = ttk.Frame(self, padding="20 20 20 20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Azusa Detector", font=('Helvetica', 18, 'bold')).pack(pady=10)

        ttk.Label(main_frame, text="Select Window:").pack(pady=5)
        self.window_combo = ttk.Combobox(main_frame, textvariable=self.window_var, width=30)
        window_titles = gw.getAllTitles()
        self.window_combo['values'] = window_titles
        self.window_combo.pack(pady=5)

        # Default Window :: OBS
        obs_windows = [title for title in window_titles if "OBS" in title]
        if obs_windows:
            self.window_var.set(obs_windows[0])

        ttk.Label(main_frame, text="Circle Radius:").pack(pady=5)
        radius_frame = ttk.Frame(main_frame)
        radius_frame.pack(pady=5)
        ttk.Entry(radius_frame, textvariable=self.radius_var, width=5).pack(side=tk.LEFT, padx=5)
        ttk.Button(radius_frame, text="-", command=self.decrease_radius, width=2).pack(side=tk.LEFT)
        ttk.Button(radius_frame, text="+", command=self.increase_radius, width=2).pack(side=tk.LEFT)

        ttk.Button(main_frame, text="Start Monitoring", command=self.start_monitoring, style='Accent.TButton').pack(pady=20)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(main_frame, textvariable=self.status_var, font=('Helvetica', 10, 'italic')).pack(pady=10)

    def decrease_radius(self):
        current = int(self.radius_var.get())
        self.radius_var.set(str(max(1, current - 1)))

    def increase_radius(self):
        current = int(self.radius_var.get())
        self.radius_var.set(str(current + 1))

    def start_monitoring(self):
        window_title = self.window_var.get()
        circle_radius = int(self.radius_var.get())
        self.status_var.set("Monitoring started...")
        self.destroy()  # Close the GUI window
        threading.Thread(target=main, args=(window_title, circle_radius)).start()


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
    roi = frame[y:y + h, x:x + w]

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
    unique_alias = f"alert_sound_{time.time()}"
    windll.winmm.mciSendStringW(f"open {SOUND_FILE} alias {unique_alias}", None, 0, None)
    windll.winmm.mciSendStringW(f"play {unique_alias}", None, 0, None)
    time.sleep(1)
    windll.winmm.mciSendStringW(f"close {unique_alias}", None, 0, None)

def capture_window(hwnd):
    left, top, right, bot = win32gui.GetClientRect(hwnd)
    width = right - left
    height = bot - top

    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)

    saveDC.SelectObject(saveBitMap)

    result = windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 3)

    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)

    img = np.frombuffer(bmpstr, dtype='uint8')
    img.shape = (height, width, 4)

    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    return img

def main(window_title, circle_radius):
    target_window = gw.getWindowsWithTitle(window_title)[0]
    hwnd = win32gui.FindWindow(None, window_title)

    initial_rectangle = None
    is_recording = False
    is_muted = False
    record_data = []
    start_time = None
    was_outside = False

    while True:
        screenshot = capture_window(hwnd)
        frame = cv2.cvtColor(screenshot, cv2.COLOR_RGBA2BGR)

        if initial_rectangle is None:
            initial_rectangle, frame = detect_black_rectangle(frame)

        if initial_rectangle:
            x, y, w, h = initial_rectangle
            circle_center = draw_circle(frame, initial_rectangle, circle_radius)
            is_outside, white_point = check_white_point_outside_circle(frame, initial_rectangle, circle_center, circle_radius)

            if is_outside and not was_outside:
                threading.Thread(target=play_alert_sound, args=(is_muted,)).start()
                print("(ᓀ‸ᓂ)")

            was_outside = is_outside

            if is_recording:
                current_time = (datetime.now() - start_time).total_seconds()
                if white_point:
                    record_data.append([current_time, is_outside, white_point[0], white_point[1], w, h])
                else:
                    record_data.append([current_time, is_outside, None, None, w, h])

        cv2.putText(frame, f"Circle Radius: {circle_radius}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        if is_recording:
            elapsed_time = (datetime.now() - start_time).total_seconds()
            minutes, seconds = divmod(int(elapsed_time), 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            cv2.putText(frame, f"Recording: Yes ({time_str})", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
        else:
            cv2.putText(frame, "Recording: No", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        mute_color = (0, 0, 255) if is_muted else (255, 255, 255)
        cv2.putText(frame, f"Muted: {'Yes' if is_muted else 'No'}", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, mute_color, 2)

        cv2.imshow("Display", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('+') or key == ord('='):
            circle_radius += 1
        elif key == ord('-') or key == ord('_'):
            circle_radius = max(1, circle_radius - 1)
        elif key == ord('r'):
            if not is_recording:
                is_recording = True
                start_time = datetime.now()
                record_data.clear()
            else:
                is_recording = False
                save_record_data(record_data, initial_rectangle)
        elif key == ord('m'):
            is_muted = not is_muted
            print(f"Mute {'enabled' if is_muted else 'disabled'}")

    cv2.destroyAllWindows()

def save_record_data(data, rectangle):
    folder_name = "azusa_record"
    os.makedirs(folder_name, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(folder_name, f"record_{timestamp}.csv")

    with open(filename, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Rectangle Size", f"{rectangle[2]}x{rectangle[3]}"])
        writer.writerow(["Time (s)", "Is Outside", "X", "Y", "Rectangle Width", "Rectangle Height"])
        writer.writerows(data)
    print(f"Record saved to {filename}")

if __name__ == "__main__":
    app = App()
    app.mainloop()