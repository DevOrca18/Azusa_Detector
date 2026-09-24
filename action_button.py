"""Small native buttons with drawn icons, key caps and translated tooltips."""
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk
from ui_theme import PALETTE


def icon_image(master, name, color):
    scale = 4
    bitmap = Image.new("RGBA", (24 * scale, 24 * scale))
    draw = ImageDraw.Draw(bitmap)

    def box(bounds):
        return tuple(round(n * scale) for n in bounds)

    def line(points):
        draw.line(box(points), fill=color, width=2 * scale, joint="curve")

    def circle(bounds, fill=None):
        draw.ellipse(box(bounds), outline=color, fill=fill, width=2 * scale)

    if name in ("play", "sample_stop"):
        draw.rounded_rectangle(box((2, 3, 22, 21)), 3 * scale, outline=color, width=2 * scale)
        if name == "play":
            draw.polygon(box((9, 7, 9, 17, 17, 12)), fill=color)
        else:
            draw.rectangle(box((8, 8, 16, 16)), fill=color)
    elif name == "record":
        circle((4, 4, 20, 20))
        circle((8, 8, 16, 16), color)
    elif name == "recording":
        circle((3, 3, 21, 21))
        draw.rounded_rectangle(box((8, 8, 16, 16)), 1 * scale, fill=color)
    elif name in ("sound", "muted"):
        draw.polygon(box((3, 9, 7, 9, 12, 5, 12, 19, 7, 15, 3, 15)), fill=color)
        if name == "sound":
            draw.arc(box((9, 6, 20, 18)), -55, 55, fill=color, width=2 * scale)
            draw.arc(box((6, 2, 24, 22)), -45, 45, fill=color, width=2 * scale)
        else:
            line((16, 9, 22, 15))
            line((22, 9, 16, 15))
    elif name == "calibrate":
        draw.rounded_rectangle(box((3, 5, 21, 20)), 2 * scale, outline=color, width=2 * scale)
        line((8, 5, 9, 2, 15, 2, 16, 5))
        circle((8, 8, 17, 17))
        line((12, 10, 12, 13, 15, 13))
    elif name == "saved":
        circle((2, 2, 22, 22))
        line((6, 12, 10, 16, 18, 8))
    elif name == "stop":
        draw.rounded_rectangle(box((5, 5, 19, 19)), 2 * scale, fill=color)
    elif name == "refresh":
        draw.arc(box((4, 4, 20, 20)), 35, 310, fill=color, width=2 * scale)
        draw.polygon(box((16, 2, 22, 3, 21, 9)), fill=color)
    elif name == "detect":
        circle((5, 5, 19, 19))
        for points in ((12, 1, 12, 8), (12, 16, 12, 23), (1, 12, 8, 12), (16, 12, 23, 12)):
            line(points)
    return ImageTk.PhotoImage(bitmap.resize((24, 24), Image.Resampling.LANCZOS), master=master)


class ActionButton(ttk.Button):
    def __init__(self, parent, key, command):
        super().__init__(parent, text=key, compound="top", style="Icon.TButton", command=command)
        self.images = {}
        self.tip_text = ""
        self.tip = None
        self.tip_after = None
        self.display_state = None
        for event in ("<Enter>", "<FocusIn>"):
            self.bind(event, self.schedule_tip, add="+")
        for event in ("<Leave>", "<FocusOut>", "<ButtonPress>", "<Destroy>"):
            self.bind(event, self.hide_tip, add="+")

    def set_status(self, icon, label, enabled=True, active=False):
        self.tip_text = label
        color = PALETTE["pink"] if active and icon == "recording" else PALETTE["gold"] if active else PALETTE["silver"]
        if not enabled:
            color = "#777180"
        state = (icon, color, enabled)
        if state != self.display_state:
            self.display_state = state
            if (icon, color) not in self.images:
                self.images[icon, color] = icon_image(self, icon, color)
            self.configure(image=self.images[icon, color])
            self.state(["!disabled"] if enabled else ["disabled"])

    def schedule_tip(self, event=None):
        self.hide_tip()
        self.tip_after = self.after(350, self.show_tip)

    def show_tip(self):
        self.tip_after = None
        if not self.winfo_exists():
            return
        self.tip = tk.Toplevel(self)
        self.tip.wm_overrideredirect(True)
        self.tip.attributes("-topmost", True)
        label = tk.Label(self.tip, text=self.tip_text, bg=PALETTE["field"], fg=PALETTE["ivory"],
                         font=("Malgun Gothic", 9), padx=9, pady=6, relief="solid", borderwidth=1)
        label.pack()
        self.tip.update_idletasks()
        x = min(self.winfo_rootx(), self.winfo_screenwidth() - self.tip.winfo_reqwidth() - 8)
        self.tip.geometry(f"+{max(0, x)}+{max(0, self.winfo_rooty() - self.tip.winfo_reqheight() - 6)}")

    def hide_tip(self, event=None):
        if self.tip_after is not None:
            self.after_cancel(self.tip_after)
            self.tip_after = None
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None
