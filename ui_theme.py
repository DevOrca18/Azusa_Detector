"""Azusa's silver, lilac and champagne desktop theme."""
import tkinter as tk
from tkinter import ttk
import webbrowser
from pathlib import Path

from PIL import Image, ImageDraw, ImageTk
from localization import t
from activity_log import LogView

REPOSITORY_URL = "https://github.com/DevOrca18/Azusa_Detector"
USER_GUIDE_URL = REPOSITORY_URL + "#readme"


PALETTE = {
    "bg": "#18171F", "panel": "#2B2A35", "deep": "#0F0F15",
    "field": "#1C1A24", "border": "#454050", "silver": "#DCDCEA",
    "muted": "#B1A9BF", "lilac": "#A487C4", "purple": "#66648A",
    "gold": "#EFC997", "ivory": "#FBF1E4", "pink": "#BD90A5",
    "warning": "#F0A0B2", "safe": "#BFCFAE",
}


def configure_theme(root):
    p = PALETTE
    style = root.style
    # Clam honors custom colors consistently; image-backed themes paint over them.
    style.theme_use("clam")
    root.configure(background=p["bg"])
    for name, value in (("background", p["field"]), ("foreground", p["silver"]),
                        ("selectBackground", p["purple"]), ("selectForeground", p["ivory"])):
        root.option_add(f"*TCombobox*Listbox.{name}", value)
    style.configure(".", font=("Malgun Gothic", 9), background=p["panel"], foreground=p["silver"])
    style.configure("App.TFrame", background=p["bg"])
    style.configure("Card.TFrame", background=p["panel"])
    style.configure("TLabel", background=p["panel"], foreground=p["silver"])
    style.configure("Section.TLabel", background=p["panel"], foreground=p["silver"])
    style.configure("Title.TLabel", background=p["bg"], foreground=p["ivory"], font=("Malgun Gothic", 18, "bold"))
    style.configure("Subtitle.TLabel", background=p["bg"], foreground=p["muted"], font=("Malgun Gothic", 9))
    style.configure("Eyebrow.TLabel", background=p["bg"], foreground=p["lilac"], font=("Segoe UI", 9, "bold"))
    style.configure("Status.TLabel", background=p["bg"], foreground=p["muted"], font=("Malgun Gothic", 9))
    style.configure("Hint.TLabel", background=p["panel"], foreground=p["muted"], font=("Malgun Gothic", 9))
    style.configure("Error.TLabel", background=p["panel"], foreground=p["warning"], font=("Malgun Gothic", 9))
    style.configure("Metric.TLabel", background=p["panel"], foreground=p["ivory"], font=("Malgun Gothic", 9, "bold"))
    style.configure("Metric.TFrame", background=p["field"])
    style.configure("MetricCaption.TLabel", background=p["field"], foreground=p["muted"], font=("Malgun Gothic", 9))
    style.configure("MetricValue.TLabel", background=p["field"], foreground=p["ivory"], font=("Consolas", 11, "bold"))
    style.configure("Badge.TLabel", background="#343040", foreground=p["gold"], padding=(12, 6), font=("Malgun Gothic", 9, "bold"))
    style.configure("Section.TLabelframe", background=p["panel"], bordercolor=p["border"],
                    lightcolor=p["panel"], darkcolor=p["panel"], relief="solid", borderwidth=1)
    style.configure("Section.TLabelframe.Label", background=p["panel"], foreground=p["gold"], font=("Malgun Gothic", 9, "bold"))
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=p["panel"], foreground=p["silver"], indicatorbackground=p["field"],
                        indicatorforeground=p["gold"], padding=(0, 3))
        style.map(name, background=[("active", p["panel"])], foreground=[("disabled", "#817A90")],
                  indicatorbackground=[("selected", p["lilac"]), ("active", p["purple"])])
    for name in ("TEntry", "TCombobox"):
        style.configure(name, fieldbackground=p["field"], background=p["field"], foreground=p["silver"],
                        insertcolor=p["ivory"], arrowcolor=p["lilac"], bordercolor=p["border"],
                        lightcolor=p["field"], darkcolor=p["field"], padding=(7, 5), borderwidth=1)
        style.map(name, fieldbackground=[("disabled", "#25232D"), ("readonly", p["field"])],
                  foreground=[("disabled", "#817A90"), ("readonly", p["silver"])],
                  bordercolor=[("focus", p["lilac"])], selectbackground=[("readonly", p["field"])],
                  selectforeground=[("readonly", p["silver"])])
    style.configure("TButton", background="#3A3448", foreground=p["silver"], bordercolor=p["border"],
                    lightcolor="#3A3448", darkcolor="#3A3448", padding=(12, 8), borderwidth=1, focusthickness=1, focuscolor=p["lilac"])
    style.map("TButton", background=[("pressed", "#494059"), ("active", "#494059")],
              bordercolor=[("focus", p["lilac"]), ("active", p["lilac"])], foreground=[("disabled", "#817A90")])
    style.configure("Primary.TButton", background=p["gold"], foreground=p["deep"], bordercolor=p["gold"],
                    lightcolor=p["gold"], darkcolor=p["gold"], font=("Malgun Gothic", 10, "bold"), padding=(18, 9))
    style.map("Primary.TButton", background=[("disabled", "#45434D"), ("pressed", "#D9B084"), ("active", "#FBDFB7")],
              foreground=[("disabled", "#918D9A"), ("!disabled", p["deep"])],
              lightcolor=[("disabled", "#45434D")], darkcolor=[("disabled", "#45434D")],
              bordercolor=[("disabled", "#45434D"), ("focus", p["ivory"]), ("active", p["ivory"])])
    style.configure("Invalid.TCombobox", bordercolor=p["warning"])
    style.map("Invalid.TCombobox", bordercolor=[("!disabled", p["warning"])])
    style.configure("Invalid.TEntry", bordercolor=p["warning"])
    style.map("Invalid.TEntry", bordercolor=[("!disabled", p["warning"])])
    style.layout("Mode.TRadiobutton", style.layout("TButton"))
    style.configure("Mode.TRadiobutton", background=p["field"], foreground=p["muted"], padding=(14, 12),
                    anchor="center", font=("Malgun Gothic", 9, "bold"), bordercolor=p["border"],
                    lightcolor=p["field"], darkcolor=p["field"], focuscolor=p["gold"])
    style.map("Mode.TRadiobutton", background=[("selected", "#514260"), ("active", "#393142")],
              foreground=[("selected", p["ivory"])], bordercolor=[("selected", p["lilac"]), ("focus", p["gold"])])
    style.configure("Vertical.TScrollbar", background=p["lilac"], troughcolor=p["field"],
                    bordercolor=p["bg"], lightcolor=p["lilac"], darkcolor=p["lilac"],
                    arrowcolor=p["silver"], arrowsize=12, width=12)
    style.map("Vertical.TScrollbar", background=[("pressed", p["gold"]), ("active", p["silver"])],
              lightcolor=[("active", p["silver"])], darkcolor=[("active", p["silver"])])
    style.configure("TSeparator", background=p["border"])
    style.configure("TNotebook", background=p["bg"], borderwidth=0)
    style.configure("TNotebook.Tab", background=p["field"], foreground=p["muted"], padding=(18, 10))
    style.map("TNotebook.Tab", background=[("selected", p["panel"])], foreground=[("selected", p["gold"])])
    install_rounded_elements(root)


def install_rounded_elements(root):
    """Nine-slice native ttk surfaces: rounded paint, standard keyboard behavior."""
    style, p = root.style, PALETTE
    root._skin_generation = getattr(root, "_skin_generation", 0) + 1
    prefix = f"Azusa{root._skin_generation}"
    root._skin_images = []

    def surface(fill, outline, surround, radius=8):
        scale, size = 4, 32
        bitmap = Image.new("RGB", (size * scale, size * scale), surround)
        draw = ImageDraw.Draw(bitmap)
        draw.rounded_rectangle((2, 2, size * scale - 3, size * scale - 3), radius * scale,
                               fill=fill, outline=outline, width=scale)
        photo = ImageTk.PhotoImage(bitmap.resize((size, size), Image.Resampling.LANCZOS), master=root)
        root._skin_images.append(photo)
        return photo

    def button(name, surround, fill, outline, hover, foreground, selected=None):
        element = prefix + name.replace(".", "") + ".border"
        ribbon_path = Path(__file__).parent / "assets" / "ui" / "start-ribbon-v1.png"
        ribbon = None
        if name == "Primary.TButton" and ribbon_path.exists():
            with Image.open(ribbon_path) as artwork:
                ribbon = artwork.convert("RGBA")
                ribbon = ribbon.crop(ribbon.getbbox())
                ribbon = ribbon.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        def decorated_surface(color, edge, faded=False):
            # Render the generated transparent artwork into the native ttk skin;
            # its top-left slice stays fixed when the translated button widens.
            scale = 4
            bitmap = Image.new("RGBA", (92 * scale, 54 * scale), surround)
            draw = ImageDraw.Draw(bitmap)
            # The mirrored bow's knot is at 50%, 44% of its cropped bounds.
            # Anchor that knot to the button's top-left border corner.
            draw.rounded_rectangle((21 * scale, 18.5 * scale, 92 * scale - 2, 54 * scale - 2),
                                   8 * scale, fill=color, outline=edge, width=2 * scale)
            bow = ribbon.resize((42 * scale, 42 * scale), Image.Resampling.LANCZOS)
            if faded:
                bow.putalpha(bow.getchannel("A").point(lambda opacity: int(opacity * 0.35)))
            bitmap.alpha_composite(bow, (0, 0))
            photo = ImageTk.PhotoImage(bitmap.resize((92, 54), Image.Resampling.LANCZOS), master=root)
            root._skin_images.append(photo)
            return photo

        if ribbon is not None:
            normal = decorated_surface(fill, outline)
            disabled = decorated_surface("#45434D", "#45434D", True)
            active = decorated_surface(hover, outline)
            focused = decorated_surface(fill, "#FFE8A3")
        else:
            normal = surface(fill, outline, surround)
            disabled = surface("#45434D", "#45434D", surround)
            active = surface(hover, hover, surround)
            focused = surface(fill, p["gold"], surround)
        specs = [("disabled", disabled), ("pressed", active)]
        if selected:
            specs.append(("selected", surface(selected, p["lilac"], surround)))
        specs.extend((("active", active), ("focus", focused)))
        style.element_create(element, "image", normal, *specs, border=(44, 42, 9, 9) if ribbon is not None else 8, padding=0, sticky="nsew")
        style.layout(name, [(element, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
        style.configure(name, foreground=foreground, background=fill, padding=(12, 7), anchor="center")
        style.map(name, foreground=[("disabled", "#918D9A"), ("!disabled", foreground)])

    button("TButton", p["panel"], "#3A3448", p["border"], "#494059", p["silver"])
    button("Primary.TButton", p["bg"], "#7954B3", "#F1D17B", "#8B65C4", p["ivory"])
    style.configure("Primary.TButton", padding=(44, 23, 14, 8))
    button("Icon.TButton", p["panel"], p["field"], p["border"], "#494059", p["muted"])
    style.configure("Icon.TButton", padding=(10, 6), width=4, font=("Segoe UI", 8))
    button("Gold.TButton", p["bg"], p["gold"], p["gold"], "#FBDFB7", p["deep"])
    style.configure("Gold.TButton", font=("Malgun Gothic", 9, "bold"))
    button("Mode.TRadiobutton", p["panel"], p["field"], p["border"], "#393142", p["silver"], "#514260")
    button("View.TRadiobutton", p["bg"], p["field"], p["border"], "#393142", p["silver"], "#514260")
    style.configure("View.TRadiobutton", font=("Malgun Gothic", 9, "bold"), width=12, padding=(12, 8))
    button("Sidebar.TButton", p["deep"], p["deep"], "#36313F", "#302A3C", p["silver"])
    style.configure("Sidebar.TButton", font=("Segoe UI", 10), padding=(10, 0))
    for name, fill, surround in (("Rounded.TFrame", p["panel"], p["bg"]),
                                 ("Metric.TFrame", p["field"], p["panel"])):
        element = prefix + name.replace(".", "") + ".border"
        photo = surface(fill, p["border"] if name == "Rounded.TFrame" else fill, surround, 10)
        style.element_create(element, "image", photo, border=12, padding=0, sticky="nsew")
        style.layout(name, [(element, {"sticky": "nsew"})])
        style.configure(name, background=fill)
    style.configure("CardTitle.TLabel", background=p["panel"], foreground=p["silver"], font=("Malgun Gothic", 9, "bold"))
    style.configure("Step.TLabel", background=p["panel"], foreground=p["gold"], font=("Segoe UI", 10, "bold"))


class SectionCard(ttk.Frame):
    def __init__(self, parent, title, step):
        super().__init__(parent, style="Rounded.TFrame", padding=12)
        self.columnconfigure(0, weight=1)
        heading = ttk.Frame(self, style="Card.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(heading, text=step, style="Step.TLabel").pack(side="left", padx=(0, 10))
        ttk.Label(heading, text=title, style="CardTitle.TLabel").pack(side="left")
        self.content = ttk.Frame(self, style="Card.TFrame")
        self.content.grid(row=1, column=0, sticky="ew")


def bgr(name):
    value = PALETTE[name].lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (4, 2, 0))


class BrandRail(tk.Canvas):
    def __init__(self, parent, image_path, open_records, activity):
        super().__init__(parent, width=184, highlightthickness=0, bg=PALETTE["deep"])
        self.art = None
        try:
            with Image.open(image_path) as source:
                self.art = source.convert("RGB")
        except OSError:
            pass  # Controls remain usable if a local artwork file is missing.
        self.photo = None
        self.photo_size = None
        self.bind("<Configure>", self.redraw)
        self.github_icon = None
        icon = Path(image_path).with_name("github.png")
        if icon.exists():
            self.github_icon = ImageTk.PhotoImage(Image.open(icon).resize((20, 20), Image.Resampling.LANCZOS), master=self)
        self.repository_button = ttk.Button(self, text="  " + t("사용법") + "   ↗", image=self.github_icon, compound="left", style="Sidebar.TButton", command=lambda: webbrowser.open_new_tab(USER_GUIDE_URL))
        self.records_button = ttk.Button(self, text=t("기록 폴더") + "   ↗", style="Sidebar.TButton", command=open_records)
        self.log_view = LogView(self, activity, PALETTE)

    def redraw(self, *_):
        p = PALETTE
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        self.create_line(28, 36, 66, 36, fill=p["gold"], width=2)
        self.create_text(28, 58, text="AZUSA", anchor="nw", fill=p["silver"], font=("Segoe UI", 24, "bold"))
        self.create_text(26, 103, text="D E T E C T O R", anchor="nw", fill=p["gold"], font=("Segoe UI", 10))
        art_bottom = 140
        if self.art is not None:
            # Reserve usable log space even in a shorter window.
            art_height = max(100, min(round(w * self.art.height / self.art.width), h - 430))
            size = (max(1, round(art_height * self.art.width / self.art.height)), art_height)
            if self.photo_size != size:
                self.photo = ImageTk.PhotoImage(self.art.resize(size, Image.Resampling.LANCZOS), master=self)
                self.photo_size = size
            self.create_image(w / 2, 140, image=self.photo, anchor="n")
            art_bottom += size[1]
        log_top = art_bottom + 14
        self.create_window(w / 2, log_top, window=self.log_view, width=max(1, w - 24),
                           height=max(60, h - 193 - log_top), anchor="n")
        self.create_line(24, h - 177, w - 24, h - 177, fill=p["border"])
        self.create_window(w / 2, h - 160, window=self.records_button, width=max(1, w - 48), height=42, anchor="n")
        self.create_window(w / 2, h - 106, window=self.repository_button, width=max(1, w - 48), height=42, anchor="n")
        self.create_text(28, h - 38, text="@DevOrca18", anchor="nw", fill=p["muted"], font=("Segoe UI", 9))


class ScrollableSettings(ttk.Frame):
    """Only the form scrolls; preview and launch controls remain visible."""
    def __init__(self, parent):
        super().__init__(parent, style="App.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg=PALETTE["bg"], highlightthickness=0, width=360)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.inner = ttk.Frame(self.canvas, style="App.TFrame")
        self.inner.columnconfigure(0, weight=1)
        self.item = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self.refresh)
        self.canvas.bind("<Configure>", self.resize)
        self.wheel_binding = self.winfo_toplevel().bind("<MouseWheel>", self.wheel, add="+")
        self.bind("<Destroy>", self.cleanup, add="+")

    def cleanup(self, event):
        if event.widget is self:
            self.winfo_toplevel().unbind("<MouseWheel>", self.wheel_binding)

    def resize(self, event):
        self.canvas.itemconfigure(self.item, width=event.width)
        self.refresh()

    def refresh(self, *_):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self.inner.winfo_reqheight() > self.canvas.winfo_height() + 1:
            self.scrollbar.grid()
        else:
            self.scrollbar.grid_remove()
            self.canvas.yview_moveto(0)

    def wheel(self, event):
        widget = event.widget
        # Let open combo lists and widgets outside this column keep their input.
        while widget is not None and widget is not self:
            if isinstance(widget, ttk.Combobox):
                return
            widget = getattr(widget, "master", None)
        if widget is self and self.inner.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
            return "break"


class ToggleSwitch(tk.Canvas):
    def __init__(self, parent, variable, compact=False):
        super().__init__(parent, width=74, height=32, highlightthickness=0, bg=PALETTE["panel"], cursor="hand2", takefocus=True)
        self.compact = compact
        if compact:
            self.configure(width=58, height=26)
        self.variable = variable
        self.trace = variable.trace_add("write", self.redraw)
        self.bind("<Button-1>", self.toggle)
        self.bind("<space>", self.toggle)
        self.bind("<Return>", self.toggle)
        self.bind("<FocusIn>", self.redraw)
        self.bind("<FocusOut>", self.redraw)
        self.bind("<Destroy>", self.cleanup)
        self.redraw()

    def cleanup(self, event):
        if event.widget is self:
            self.variable.trace_remove("write", self.trace)

    def toggle(self, event=None):
        self.focus_set()
        self.variable.set(not self.variable.get())
        return "break"

    def redraw(self, *_):
        self.delete("all")
        on = self.variable.get()
        color = PALETTE["lilac"] if on else PALETTE["border"]
        self.create_oval(2, 3, 28, 29, fill=color, outline="")
        self.create_rectangle(15, 3, 59, 29, fill=color, outline="")
        self.create_oval(46, 3, 72, 29, fill=color, outline="")
        center = 59 if on else 15
        self.create_oval(center - 10, 6, center + 10, 26, fill=PALETTE["ivory"], outline="")
        self.create_text(27 if on else 47, 16, text="ON" if on else "OFF", fill=PALETTE["deep"] if on else PALETTE["silver"], font=("Segoe UI", 9, "bold"))
        if self.focus_get() is self:
            self.create_rectangle(1, 1, 73, 31, outline=PALETTE["gold"], dash=(2, 2))
        if self.compact:
            self.scale("all", 0, 0, 58 / 74, 26 / 32)
