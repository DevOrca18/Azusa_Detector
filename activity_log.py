"""Bounded, thread-safe activity history; only the UI renders Tk widgets."""
from collections import deque
from datetime import datetime
import queue
import tkinter as tk

from localization import t


class ActivityLog:
    def __init__(self, limit=300):
        self.history = deque(maxlen=limit)
        self.pending = queue.Queue(maxsize=512)

    def emit(self, key, level="info", **values):
        entry = (datetime.now().strftime("%H:%M:%S"), key, level, values)
        try:
            self.pending.put_nowait(entry)
        except queue.Full:
            try:
                self.pending.get_nowait()
            except queue.Empty:
                pass
            try:
                self.pending.put_nowait(entry)
            except queue.Full:
                pass

    def drain(self):
        entries = []
        for _ in range(100):
            try:
                entry = self.pending.get_nowait()
            except queue.Empty:
                break
            self.history.append(entry)
            entries.append(entry)
        return entries

    @staticmethod
    def format(entry):
        timestamp, key, _, values = entry
        values = {name[:-4] if name.endswith("_key") else name:
                  t(value) if name.endswith("_key") else value for name, value in values.items()}
        return f"[{timestamp}] {t(key, **values)}\n"


class LogView(tk.Frame):
    def __init__(self, parent, activity, palette):
        super().__init__(parent, bg=palette["deep"])
        self.activity = activity
        self.line_counts = deque()
        tk.Label(self, text=t("활동 로그"), bg=palette["deep"], fg=palette["gold"],
                 font=("Malgun Gothic", 8, "bold"), anchor="w").pack(fill="x", pady=(0, 5))
        self.text = tk.Text(self, bg=palette["field"], fg=palette["muted"], borderwidth=0,
                            highlightthickness=1, highlightbackground=palette["border"],
                            font=("Malgun Gothic", 8), wrap="word", padx=6, pady=6,
                            insertwidth=0, state="disabled", cursor="arrow", takefocus=True,
                            width=1, height=1)
        self.text.pack(fill="both", expand=True)
        self.text.tag_configure("error", foreground=palette["warning"])
        self.text.tag_configure("sound", foreground=palette["gold"])
        self.text.tag_configure("info", foreground=palette["muted"])
        # Existing history is translated again when the language rebuilds this view.
        self.append(list(activity.history))

    def append(self, entries):
        if not entries:
            return
        follow = self.text.yview()[1] >= 0.98
        self.text.configure(state="normal")
        for entry in entries:
            text = self.activity.format(entry)
            self.text.insert("end", text, entry[2])
            self.line_counts.append(text.count("\n"))
            if len(self.line_counts) > self.activity.history.maxlen:
                self.text.delete("1.0", f"{1 + self.line_counts.popleft()}.0")
        self.text.configure(state="disabled")
        if follow:
            self.text.see("end")
