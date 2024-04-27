import threading
from ctypes import windll

import cv2
import numpy as np
import pygetwindow as gw
import pyautogui
import time

# Initial analysis video area (Black Rectangular)
def detect_black_rectangle(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        max_contour = max(contours, key=cv2.contourArea)
        x, y, w, h = cv2.boundingRect(max_contour)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

        return (x, y, w, h), frame # Save Coordinates

    return None, frame

# Draw Yellow Circle (Valid area)
def draw_circle(frame, rect, circle_radius):
    x, y, w, h = rect
    circle_center = (x + w // 2, y + h // 2)
    cv2.circle(frame, circle_center, circle_radius, (0, 255, 255), 2)

    return circle_center, circle_radius

# Check if there are white points outside the circle and inside the black rectangle.
def check_white_point_outside_circle(frame, rect, circle_center, circle_radius):
    x, y, w, h = rect
    roi = frame[y:y + h, x:x + w]  # Area of the black rectangle

    # Detecting the inside of the circle using a mask
    mask = np.zeros(roi.shape[:2], dtype=np.uint8)
    cv2.circle(mask, (circle_center[0] - x, circle_center[1] - y), circle_radius, (255, 255, 255), -1)  # Inside

    # Detecting white pixels inside the black rectangle
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_white = np.array([0, 0, 200])
    upper_white = np.array([180, 25, 255])
    white_pixels = cv2.inRange(hsv, lower_white, upper_white)

    # Detecting white pixels outside the circle
    outside_white_pixels = cv2.bitwise_and(white_pixels, cv2.bitwise_not(mask))  # White pixels outside the circle

    # Check if white pixels are outside the circle and inside the black rectangle
    if np.any(outside_white_pixels):
        return True  # Return True if there are white points outside the circle
    return False  # Return False if there are no white points outside the circle



# Play Sound
def play_alert_sound():
    sound_file = "alert.wav"
    unique_alias = f"alert_sound_{time.time()}"

    windll.winmm.mciSendStringW(f"open {sound_file} alias {unique_alias}", None, 0, None)
    windll.winmm.mciSendStringW(f"play {sound_file}", None, 0, None)

    time.sleep(1)
    windll.winmm.mciSendStringW(f"close {unique_alias}", None, 0, None)
def threaded_play_alert_sound():
    sound_thread = threading.Thread(target=lambda: play_alert_sound())
    sound_thread.start()


def main():
    open_windows = gw.getAllTitles()

    print("Windows List")
    for i, window in enumerate(open_windows):
        print(f"{i + 1}. {window}")

    # Select window
    choice = int(input("Select the window to monitor (enter the number) :"))

    target_window_title = open_windows[choice - 1]

    while True:
        target_windows = gw.getWindowsWithTitle(target_window_title)
        if target_windows:
            target_window = target_windows[0]
            break
        else:
            print("Window not found. Please wait a moment.")

    # Set circle size
    circle_radius = int(input("Specify the circle radius (enter the number) : "))
    initial_rectangle = None

    while True:
        screenshot = pyautogui.screenshot(
            region=(target_window.left, target_window.top, target_window.width, target_window.height)
        )

        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        if initial_rectangle is None:
            # Black box
            initial_rectangle, frame = detect_black_rectangle(frame)

        if initial_rectangle:
            # Draw circle
            circle_center, _ = draw_circle(frame, initial_rectangle, circle_radius)

            # Detect white dot
            is_outside = check_white_point_outside_circle(frame, initial_rectangle, circle_center, circle_radius)

            if is_outside:
                threaded_play_alert_sound()
                print("(ᓀ‸ᓂ)")

        cv2.imshow("Display", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break  # 'q' to quit

    cv2.destroyAllWindows()  # OpenCV close

if __name__ == "__main__":
    main()
