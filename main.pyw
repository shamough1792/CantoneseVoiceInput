import time
import os
import sys
import json
import ctypes
import threading
import queue
import winsound
import tkinter as tk
from tkinter import messagebox
import traceback
from pynput import keyboard
from pynput.keyboard import Controller as KeyboardController, Key
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

import pystray
from PIL import Image, ImageDraw, ImageTk

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000

THEME_PALETTES = {
    "dark": {"bg": "#1f1f1f", "surface": "#252525", "surface_alt": "#2a2a2a", "border": "#3c3c3c", "text": "#f3f3f3", "muted": "#8f8f8f", "accent": "#38b2a1", "mic_bg": "#2a2a2a", "mic_active": "#333333", "success": "#107c10", "warning": "#c19c00", "error": "#d13438", "hover": "#333333"},
    "light": {"bg": "#f3f3f3", "surface": "#ffffff", "surface_alt": "#e8e8e8", "border": "#d1d1d1", "text": "#1f1f1f", "muted": "#666666", "accent": "#087f70", "mic_bg": "#e8e8e8", "mic_active": "#d6e8f8", "success": "#107c10", "warning": "#9a6700", "error": "#c42b1c", "hover": "#dedede"},
}
DEFAULT_CONFIG = {"copy_to_clipboard": False, "theme": "dark"}


def normalize_theme(value):
    return value if isinstance(value, str) and value in THEME_PALETTES else "dark"


CONFIG_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'CantoneseVoiceInput')

def load_config():
    try:
        with open(os.path.join(CONFIG_DIR, 'config.json'), 'r', encoding='utf-8') as f:
            config = {**DEFAULT_CONFIG, **json.load(f)}
            config["theme"] = normalize_theme(config.get("theme"))
            return config
    except Exception:
        return dict(DEFAULT_CONFIG)

def save_config(config):
    try:
        current_config = load_config()
        current_config.update(config)
        current_config["theme"] = normalize_theme(current_config.get("theme"))
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(os.path.join(CONFIG_DIR, 'config.json'), 'w', encoding='utf-8') as f:
            json.dump(current_config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[設定] 無法儲存設定檔: {e}")


# 主題配色定義 (Windows 風格深色介面)
COLOR_BG = "#1f1f1f"         # 主背景深灰
COLOR_BORDER = "#3c3c3c"     # 邊框與分割線
COLOR_ACCENT = "#0078d4"     # Windows 藍色高亮
COLOR_ICON = "#c8c8c8"       # 圖示與文字預設灰色
COLOR_MIC_BG = "#2a2a2a"     # 麥克風底圈
COLOR_MIC_ACTIVE = "#333333"  # 錄音中麥克風底圈
COLOR_SURFACE = "#252525"     # 卡片與對話框表面
COLOR_MUTED = "#8f8f8f"       # 次要文字

SAMPLE_RATE = 44100

# 資源路徑解析：PyInstaller 凍結後讀 sys._MEIPASS，一般執行讀專案根目錄
def _resource_path(rel):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

# 提示音 WAV 檔（res/ 內嵌，免授權提示音轉為 44100Hz 16-bit mono WAV）
SOUND_FILES = {
    "start":   "res/snd_start.wav",
    "success": "res/snd_success.wav",
    "fail":    "res/snd_fail.wav",
}

def _play_wav(path):
    """背景執行緒播放 WAV 檔；失敗時靜默（檔案缺、格式不支援等）。"""
    def _play():
        try:
            winsound.PlaySound(_resource_path(path), winsound.SND_FILENAME)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()

def play_sound(sound_type="start"):
    """播放內嵌的 Google 風格提示音 WAV（res/snd_*.wav）"""
    path = SOUND_FILES.get(sound_type)
    if path:
        _play_wav(path)

def _apply_rounded_window(window, radius=18):
    """優先使用合成器的平滑圓角，不支援時才使用區域裁切。"""
    try:
        window.update_idletasks()
        user32 = ctypes.windll.user32
        get_ancestor = user32.GetAncestor
        get_ancestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        get_ancestor.restype = ctypes.c_void_p
        inner_hwnd = window.winfo_id()
        hwnd = get_ancestor(inner_hwnd, 2) or inner_hwnd
        set_region = user32.SetWindowRgn
        set_region.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        set_region.restype = ctypes.c_int

        try:
            set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
            set_attribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
            set_attribute.restype = ctypes.c_long
            # 自訂區域會阻止原生圓角；Tk 內容 HWND 與外層視窗都必須清除。
            set_region(inner_hwnd, None, True)
            if hwnd != inner_hwnd:
                set_region(hwnd, None, True)
            preference = ctypes.c_int(2)  # DWMWCP_ROUND
            if set_attribute(hwnd, 33, ctypes.byref(preference), ctypes.sizeof(preference)) == 0:
                border = ctypes.c_uint(0xfffffffe)  # DWMWA_COLOR_NONE：維持無細邊框。
                set_attribute(hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))
                return True
        except (AttributeError, OSError):
            pass

        gdi32 = ctypes.windll.gdi32
        create_region = gdi32.CreateRoundRectRgn
        create_region.argtypes = [ctypes.c_int] * 6
        create_region.restype = ctypes.c_void_p
        region = create_region(0, 0, window.winfo_width() + 1,
                               window.winfo_height() + 1, radius * 2, radius * 2)
        # 成功時由系統持有區域；失敗時由我們釋放，避免 GDI 資源洩漏。
        if region and not set_region(hwnd, region, True):
            delete_region = gdi32.DeleteObject
            delete_region.argtypes = [ctypes.c_void_p]
            delete_region.restype = ctypes.c_int
            delete_region(region)
    except (AttributeError, OSError, tk.TclError):
        return False
    return False

def create_tray_icon_image():
    width, height = 32, 32
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse((2, 2, 30, 30), fill=COLOR_BG, outline=COLOR_ACCENT, width=2)
    dc.rectangle((13, 8, 19, 18), fill=COLOR_ACCENT)
    dc.arc((10, 12, 22, 22), 0, 180, fill=COLOR_ACCENT, width=2)
    dc.line((16, 22, 16, 26), fill=COLOR_ACCENT, width=2)
    dc.line((12, 26, 20, 26), fill=COLOR_ACCENT, width=2)
    return image

class DynamicHotkeyManager:
    """動態熱鍵管理器"""
    DEFAULT_HOTKEY = "<ctrl>+<alt>+v"

    def __init__(self, action_callback, default_hotkey=None):
        self.action_callback = action_callback
        self.current_hotkey_str = default_hotkey or self.DEFAULT_HOTKEY
        self.listener = None
        self._start_listener()

    def _start_listener(self):
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
        try:
            self.listener = keyboard.GlobalHotKeys({
                self.current_hotkey_str: self.action_callback
            })
            self.listener.start()
            return True
        except Exception as e:
            print(f"[快捷鍵錯誤] 無法註冊熱鍵 {self.current_hotkey_str}: {e}")
            return False

    def stop_listener(self):
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass

    def update_hotkey(self, new_hotkey_str):
        old_hotkey = self.current_hotkey_str
        self.current_hotkey_str = new_hotkey_str
        if not self._start_listener():
            self.current_hotkey_str = old_hotkey
            self._start_listener()
            return False
        return True

    def reset_to_default(self):
        return self.update_hotkey(self.DEFAULT_HOTKEY)

    def get_display_text(self):
        readable = self.current_hotkey_str.replace("<", "").replace(">", "").upper()
        return readable

def _rounded_surface(width, height, radius, fill, outline=None, outline_width=1):
    """以四倍取樣產生透明圓角表面，避免 Canvas 原始圖元的階梯邊緣。"""
    width, height = max(1, int(width)), max(1, int(height))
    radius = max(0, min(radius, width / 2, height / 2))
    scale = 4
    image = Image.new("RGBA", (width * scale, height * scale))
    ImageDraw.Draw(image).rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1),
        radius=radius * scale, fill=fill, outline=outline,
        width=max(1, int(outline_width * scale)))
    resampling = getattr(Image, "Resampling", Image)
    return image.resize((width, height), resampling.LANCZOS)


class RoundedButton(tk.Canvas):
    """抗鋸齒圓角按鈕，保留既有 config / command 用法。"""
    def __init__(self, parent, text="", command=None, width=220, height=38,
                 bg=COLOR_SURFACE, fg=COLOR_ICON, radius=10, **kwargs):
        super().__init__(parent, width=width, height=height, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, cursor="hand2", takefocus=True)
        self._text = text
        self._button_bg = bg
        self._button_fg = fg
        self._command = command
        self._radius = radius
        self._button_width = width
        self._button_height = height
        self._hovered = False
        self._pressed = False
        self._focused = False
        self._theme_owner = None
        ancestor = parent
        while ancestor is not None and self._theme_owner is None:
            self._theme_owner = getattr(ancestor, "_theme_owner", None)
            ancestor = getattr(ancestor, "master", None)
        self._draw()
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", lambda _event: self._set_hover(True))
        self.bind("<Leave>", lambda _event: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", lambda _event: self._set_focus(True))
        self.bind("<FocusOut>", lambda _event: self._set_focus(False))
        for key in ("space", "Return"):
            self.bind(f"<KeyPress-{key}>", self._press)
            self.bind(f"<KeyRelease-{key}>", self._release_key)

    def _draw(self):
        self.delete("all")
        width = self.winfo_width() if self.winfo_width() > 1 else self._button_width
        height = self.winfo_height() if self.winfo_height() > 1 else self._button_height
        r = min(self._radius, height // 2, width // 2)
        fill = self._button_bg
        if self._pressed or self._hovered:
            rgb = tuple(channel // 257 for channel in self.winfo_rgb(fill))
            target = 255 if sum(rgb) < 384 else 0
            amount = 0.16 if self._pressed else 0.07
            fill = tuple(round(channel + (target - channel) * amount) for channel in rgb)
        super().configure(bg=self.master.cget("bg"))
        surface = _rounded_surface(width, height, r, fill,
                                   outline=self._button_fg if self._focused else None)
        # Tk 不會持有 Python 圖片引用，必須保留，否則重繪後按鈕會消失。
        self._background_image = ImageTk.PhotoImage(surface, master=self)
        self.create_image(0, 0, anchor="nw", image=self._background_image)
        self.create_text(width // 2, height // 2, text=self._text,
                         fill=self._button_fg, font=("Microsoft JhengHei UI", 9, "bold"))

    def _set_hover(self, hovered):
        self._hovered = hovered
        if not hovered:
            self._pressed = False
        self._draw()

    def _set_focus(self, focused):
        self._focused = focused
        if not focused:
            self._pressed = False
        self._draw()

    def _press(self, _event=None):
        self.focus_set()
        self._pressed = True
        self._draw()

    def _release(self, event):
        invoke = self._pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self._pressed = False
        self._draw()
        if invoke:
            self._invoke()

    def _release_key(self, _event=None):
        invoke = self._pressed
        self._pressed = False
        self._draw()
        if invoke:
            self._invoke()

    def _invoke(self, _event=None):
        if self._command:
            self._command()

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf or {})
        options.update(kwargs)
        if "text" in options:
            self._text = options.pop("text")
        if "fg" in options:
            self._button_fg = options.pop("fg")
        if "bg" in options:
            self._button_bg = options.pop("bg")
            options["bg"] = self.master.cget("bg")
        if "command" in options:
            self._command = options.pop("command")
        options.pop("activebackground", None)
        options.pop("activeforeground", None)
        options.pop("relief", None)
        options.pop("highlightthickness", None)
        result = super().configure(options)
        self._draw()
        return result

    config = configure


class ToggleSwitch(tk.Canvas):
    """整列可點擊的膠囊開關，保留 BooleanVar 與設定儲存回呼。"""
    def __init__(self, parent, text, variable, palette, command=None):
        super().__init__(parent, width=312, height=36, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, cursor="hand2", takefocus=True)
        self.variable = variable
        self._text = text
        self._palette = palette
        self._command = command
        self._hovered = False
        self._focused = False
        self._pressed = False
        self._variable_trace = variable.trace_add("write", lambda *_args: self._draw())
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", lambda _event: self._set_hover(True))
        self.bind("<Leave>", lambda _event: self._set_hover(False))
        self.bind("<FocusIn>", lambda _event: self._set_focus(True))
        self.bind("<FocusOut>", lambda _event: self._set_focus(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        for key in ("space", "Return"):
            self.bind(f"<KeyPress-{key}>", self._press)
            self.bind(f"<KeyRelease-{key}>", self._release_key)
        self.bind("<Destroy>", self._cleanup)
        self._draw()

    def set_palette(self, palette):
        self._palette = palette
        self.configure(bg=self.master.cget("bg"))
        self._draw()

    def _draw(self):
        self.delete("all")
        width = self.winfo_width() if self.winfo_width() > 1 else 312
        height = self.winfo_height() if self.winfo_height() > 1 else 36
        palette = self._palette
        selected = self.variable.get()
        track_fill = palette["accent"] if selected else palette["hover" if self._hovered else "surface_alt"]
        track_outline = palette["text"] if self._focused else (None if selected else palette["muted"])
        self._track_image = ImageTk.PhotoImage(
            _rounded_surface(44, 24, 12, track_fill, track_outline), master=self)
        x, y = width - 44, (height - 24) // 2
        self.create_image(x, y, anchor="nw", image=self._track_image)
        diameter = 16 if self._pressed else 18
        knob_x = x + (32 if selected else 12) - diameter // 2
        self._knob_image = ImageTk.PhotoImage(
            _rounded_surface(diameter, diameter, diameter / 2, "#ffffff"), master=self)
        self.create_image(knob_x, height // 2 - diameter // 2, anchor="nw", image=self._knob_image)
        self.create_text(0, height // 2, anchor="w", text=self._text,
                         fill=palette["text"], width=max(1, width - 56),
                         font=("Microsoft JhengHei UI", 9))

    def _set_hover(self, hovered):
        self._hovered = hovered
        if not hovered:
            self._pressed = False
        self._draw()

    def _set_focus(self, focused):
        self._focused = focused
        if not focused:
            self._pressed = False
        self._draw()

    def _press(self, _event=None):
        self.focus_set()
        self._pressed = True
        self._draw()

    def _release(self, event):
        invoke = self._pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self._pressed = False
        self._draw()
        if invoke:
            self._invoke()

    def _release_key(self, _event=None):
        invoke = self._pressed
        self._pressed = False
        self._draw()
        if invoke:
            self._invoke()

    def _invoke(self):
        self.variable.set(not self.variable.get())
        if self._command:
            self._command()

    def _cleanup(self, event):
        if event.widget is self:
            self.variable.trace_remove("write", self._variable_trace)

class CardVoiceUI:
    def __init__(self, ui_queue, on_mic_click_callback, hotkey_manager, app, on_close_callback=None):
        self.ui_queue = ui_queue
        self.on_mic_click = on_mic_click_callback
        self.hotkey_manager = hotkey_manager
        self.app = app
        self.theme = app.theme
        self._theme_bindings = {}
        self._mic_active = False
        self._status_role = "muted"
        self.app.ui = self
        self.on_close_callback = on_close_callback
        self.root = None
        self.mic_btn_canvas = None
        self.status_label = None
        self.settings_dialog = None
        self.help_dialog = None
        
        self.is_visible = True
        self._drag_start_x = 0
        self._drag_start_y = 0

    @property
    def palette(self):
        return THEME_PALETTES[self.theme]

    def _register_theme_widget(self, window, widget, bg_role=None, fg_role=None):
        bindings = self._theme_bindings.setdefault(window, [])
        bindings[:] = [binding for binding in bindings if binding[0] is not widget]
        self._theme_bindings[window].append((widget, bg_role, fg_role))
        self._configure_theme_widget(widget, bg_role, fg_role)

    def _configure_theme_widget(self, widget, bg_role, fg_role):
        if not widget.winfo_exists():
            return
        palette = self.palette
        if isinstance(widget, ToggleSwitch):
            widget.set_palette(palette)
            return
        options = {}
        keys = widget.keys()
        if bg_role and "bg" in keys:
            options["bg"] = palette[bg_role]
        if fg_role and ("fg" in keys or isinstance(widget, RoundedButton)):
            options["fg"] = palette[fg_role]
        if "selectcolor" in keys:
            options.update(selectcolor=palette["mic_bg"], activebackground=palette["bg"], activeforeground=palette["text"])
        if options:
            widget.configure(**options)

    def _register_theme_subtree(self, window, widget, bg_role=None, fg_role=None):
        self._register_theme_widget(window, widget, bg_role, fg_role)
        for child in widget.winfo_children():
            self._register_theme_subtree(window, child, bg_role, fg_role)

    def _forget_theme_window(self, window):
        self._theme_bindings.pop(window, None)

    def _apply_theme_widgets(self):
        palette = self.palette
        if self.root and self.root.winfo_exists():
            self.root.configure(bg=palette["bg"])
        for window, bindings in list(self._theme_bindings.items()):
            if not window.winfo_exists():
                self._forget_theme_window(window)
                continue
            for widget, bg_role, fg_role in bindings:
                self._configure_theme_widget(widget, bg_role, fg_role)
        if self.mic_btn_canvas and self.mic_btn_canvas.winfo_exists():
            self._draw_mic_button(active=self._mic_active)

        for value, button in getattr(self, "_theme_buttons", {}).items():
            if button.winfo_exists():
                selected = value == self.theme
                button.configure(bg=palette["accent" if selected else "surface_alt"],
                                 fg="#ffffff" if selected else palette["text"])

    def apply_theme(self, theme):
        if not isinstance(theme, str) or theme not in THEME_PALETTES:
            return False
        self.theme = theme
        if self.root:
            self.root.after(0, self._apply_theme_widgets)
        return True

    def _hover_config(self, widget, enter_bg_role, enter_fg_role, leave_bg_role, leave_fg_role):
        def apply(bg_role, fg_role, entering=False):
            if isinstance(widget, RoundedButton):
                for bindings in self._theme_bindings.values():
                    binding = next((item for item in bindings if item[0] is widget), None)
                    if binding is not None:
                        if not entering or binding[2] in {"warning", "success", "error"}:
                            bg_role, fg_role = binding[1], binding[2]
                        break
            palette = self.palette
            widget.configure(bg=palette[bg_role], fg=palette[fg_role])
        def enter(_event):
            if isinstance(widget, RoundedButton):
                widget._set_hover(True)
            apply(enter_bg_role, enter_fg_role, entering=True)

        def leave(_event):
            if isinstance(widget, RoundedButton):
                widget._set_hover(False)
            apply(leave_bg_role, leave_fg_role)

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def start(self):
        self.root = tk.Tk()
        self.root._theme_owner = self
        self.root.title("粵語語音輸入法")
        
        self.root.attributes("-toolwindow", True)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        # 透明色鍵只能硬切像素，會令圓角呈階梯狀；外框統一交由系統合成。
        self.root.config(bg=self.palette["bg"])
        self.root.attributes("-alpha", 0.82)

        self.root.protocol("WM_DELETE_WINDOW", self.hide_ui)

        self.width = 208
        self.height = 120

        self.main_canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=self.palette["bg"],
            highlightthickness=0
        )
        self.main_canvas.pack()

        top_frame = tk.Frame(self.root, bg=COLOR_BG)
        top_frame.place(x=8, y=5, width=self.width-16, height=22)

        close_btn = tk.Label(
            top_frame,
            text="✕",
            font=("Segoe UI Symbol", 10),
            bg=COLOR_BG,
            fg=COLOR_ICON,
            cursor="hand2", padx=3, pady=0
        )
        close_btn.place(x=self.width-34, y=-1, width=18, height=18)
        close_btn.bind("<Button-1>", lambda e: self.hide_ui())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg="#d13438"))

        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=COLOR_ICON))

        mid_frame = tk.Frame(self.root, bg=COLOR_BG)
        mid_frame.place(x=8, y=29, width=self.width-16, height=52)

        setting_btn = tk.Label(mid_frame, text="⚙", font=("Segoe UI Symbol", 13), bg=COLOR_BG, fg=COLOR_ICON, cursor="hand2", padx=4)
        setting_btn.pack(side="left", padx=(8, 8))
        setting_btn.bind("<Button-1>", lambda e: self._open_settings_dialog())
        setting_btn.bind("<Enter>", lambda e: setting_btn.config(fg=COLOR_ACCENT))
        setting_btn.bind("<Leave>", lambda e: setting_btn.config(fg=COLOR_ICON))

        self.mic_btn_canvas = tk.Canvas(mid_frame, width=50, height=50, bg=COLOR_BG, highlightthickness=0, cursor="hand2")
        self.mic_btn_canvas.pack(side="left", expand=True)
        self._draw_mic_button(active=False)
        self.mic_btn_canvas.bind("<Button-1>", lambda e: self.on_mic_click())

        help_btn = tk.Label(mid_frame, text="❓", font=("Segoe UI Symbol", 11), bg=COLOR_BG, fg=COLOR_ICON, cursor="hand2", padx=4)
        help_btn.pack(side="right", padx=(8, 8))
        help_btn.bind("<Button-1>", lambda e: self._show_help())
        help_btn.bind("<Enter>", lambda e: help_btn.config(fg=COLOR_ACCENT))
        help_btn.bind("<Leave>", lambda e: help_btn.config(fg=COLOR_ICON))

        self.status_label = tk.Label(
            self.root,
            text=self.hotkey_manager.get_display_text(),
            font=("Microsoft JhengHei UI", 8, "bold"),
            bg=COLOR_BG,
            fg=COLOR_MUTED,
            anchor="center"
        )
        self.status_label.place(x=10, y=88, width=self.width-20, height=20)

        for widget in [self.main_canvas, top_frame, mid_frame]:
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._do_drag)

        for widget, bg_role, fg_role in (
            (self.main_canvas, "bg", None), (top_frame, "bg", None),
            (mid_frame, "bg", None), (close_btn, "bg", "text"),
            (setting_btn, "bg", "text"), (self.mic_btn_canvas, "bg", None),
            (help_btn, "bg", "text"), (self.status_label, "bg", "muted"),
        ):
            self._register_theme_widget(self.root, widget, bg_role, fg_role)
        self._hover_config(close_btn, "error", "text", "bg", "text")
        self._hover_config(setting_btn, "bg", "accent", "bg", "text")
        self._hover_config(help_btn, "bg", "accent", "bg", "text")

        self.root.update_idletasks()

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_pos = screen_width - self.width - 20
        y_pos = screen_height - self.height - 60
        self.root.geometry(f"{self.width}x{self.height}+{x_pos}+{y_pos}")
        _apply_rounded_window(self.root, radius=18)
        self._prevent_focus()

        self.root.after(50, self._check_queue)
        self.root.mainloop()

    def _draw_mic_button(self, active=False):
        self._mic_active = active
        self.mic_btn_canvas.delete("all")
        palette = self.palette
        bg_circle_color = palette["mic_bg"] if not active else palette["mic_active"]
        icon_color = palette["accent"]

        border_color = palette["accent"] if active else palette["border"]
        border_width = 2 if active else 1

        self._mic_background_image = ImageTk.PhotoImage(
            _rounded_surface(44, 44, 22, bg_circle_color, border_color, border_width),
            master=self.mic_btn_canvas)
        self.mic_btn_canvas.create_image(3, 3, anchor="nw", image=self._mic_background_image)

        mic_symbol = "🎙️" if not active else "⏹️"
        self.mic_btn_canvas.create_text(25, 25, text=mic_symbol, font=("Segoe UI Emoji", 13), fill=icon_color)

    def _open_settings_dialog(self):
        if self.settings_dialog is not None:
            try:
                if self.settings_dialog.winfo_exists():
                    self.settings_dialog.deiconify()
                    self.settings_dialog.lift()
                    self.settings_dialog.focus_force()
                    return
            except tk.TclError:
                self.settings_dialog = None
        dialog = tk.Toplevel(self.root)
        dialog._theme_owner = self
        self.settings_dialog = dialog
        self._register_theme_widget(dialog, dialog, "bg")
        dialog.title("設定")
        
        dialog_width = 360
        dialog_height = 430
        dialog.configure(bg=COLOR_BG)
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)
        dialog.transient(self.root)
        dialog.overrideredirect(True)
        dialog.configure(bg=COLOR_BG, highlightthickness=0)

        titlebar = tk.Frame(dialog, bg=COLOR_SURFACE, height=38)
        titlebar.pack(fill="x", side="top")
        titlebar.pack_propagate(False)
        tk.Label(
            titlebar, text="設定", font=("Microsoft JhengHei UI", 10, "bold"),
            bg=COLOR_SURFACE, fg="#f2f2f2", anchor="w"
        ).pack(side="left", padx=16)
        close_dialog_btn = tk.Label(
            titlebar, text="✕", font=("Segoe UI Symbol", 10),
            bg=COLOR_SURFACE, fg=COLOR_MUTED, cursor="hand2", padx=12
        )
        close_dialog_btn.pack(side="right", fill="y")
        close_dialog_btn.bind("<Enter>", lambda e: close_dialog_btn.config(bg="#c42b3c", fg="white"))
        close_dialog_btn.bind("<Leave>", lambda e: close_dialog_btn.config(bg=COLOR_SURFACE, fg=COLOR_MUTED))

        drag_state = {"x": 0, "y": 0}
        def start_dialog_drag(event):
            drag_state["x"], drag_state["y"] = event.x_root - dialog.winfo_x(), event.y_root - dialog.winfo_y()
        def drag_dialog(event):
            dialog.geometry(f"+{event.x_root - drag_state['x']}+{event.y_root - drag_state['y']}")
        titlebar.bind("<ButtonPress-1>", start_dialog_drag)
        titlebar.bind("<B1-Motion>", drag_dialog)

        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        center_x = int((screen_width - dialog_width) / 2)
        center_y = int((screen_height - dialog_height) / 2)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        header = tk.Frame(dialog, bg=COLOR_BG)
        header.pack(fill="x", padx=24, pady=(18, 8))
        tk.Label(
            header, text="設定", font=("Microsoft JhengHei UI", 15, "bold"),
            bg=COLOR_BG, fg="#f2f2f2", anchor="w"
        ).pack(fill="x")
        tk.Label(
            header, text="自訂快捷鍵及辨識後的輸入方式", font=("Microsoft JhengHei UI", 9),
            bg=COLOR_BG, fg="#929292", anchor="w"
        ).pack(fill="x", pady=(2, 0))

        hotkey_section = tk.Frame(dialog, bg=COLOR_MIC_BG)
        hotkey_section.pack(fill="x", padx=24, pady=(0, 12))
        tk.Label(
            hotkey_section, text="語音輸入快捷鍵", font=("Microsoft JhengHei UI", 9, "bold"),
            bg=COLOR_MIC_BG, fg="#f2f2f2", anchor="w"
        ).pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(
            hotkey_section, text="目前設定", font=("Microsoft JhengHei UI", 8),
            bg=COLOR_MIC_BG, fg="#929292", anchor="w"
        ).pack(fill="x", padx=14)

        record_btn = RoundedButton(
            hotkey_section,
            text=self.hotkey_manager.get_display_text(), 
            bg=COLOR_SURFACE,
            fg=COLOR_ACCENT, 
            width=284, height=42, radius=12
        )
        record_btn.pack(pady=(5, 10), padx=14, fill="x")
        record_btn.bind("<Enter>", lambda e: record_btn.config(bg=COLOR_ACCENT, fg="white"))
        record_btn.bind("<Leave>", lambda e: record_btn.config(bg=COLOR_SURFACE, fg=COLOR_ACCENT))

        tip_label = tk.Label(
            hotkey_section, text="點擊按鈕後按下組合鍵，全部放開即儲存",
            font=("Microsoft JhengHei UI", 8), bg=COLOR_MIC_BG, fg="#929292",
            anchor="w", justify="left"
        )
        tip_label.pack(fill="x", padx=14, pady=(0, 10))

        recording_state = {"is_recording": False, "recorded_keys": [], "pynput_listener": None}
        tip_message_timer = {"id": None}
        default_tip_text = "點擊按鈕後按下組合鍵，全部放開即儲存"

        def show_tip(text, role):
            tip_label.config(text=text)
            self._register_theme_widget(dialog, tip_label, "mic_bg", role)

        def schedule_tip_reset():
            if tip_message_timer["id"] is not None:
                try:
                    dialog.after_cancel(tip_message_timer["id"])
                except Exception:
                    pass
            tip_message_timer["id"] = dialog.after(
                3000,
                lambda: show_tip(default_tip_text, "muted")
            )

        self.hotkey_manager.stop_listener()

        def on_dialog_close():
            if tip_message_timer["id"] is not None:
                try:
                    dialog.after_cancel(tip_message_timer["id"])
                except Exception:
                    pass
            if recording_state["pynput_listener"]:
                try:
                    recording_state["pynput_listener"].stop()
                except Exception:
                    pass
            self.hotkey_manager._start_listener()
            self._forget_theme_window(dialog)
            dialog.destroy()
            self.settings_dialog = None

        dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)
        close_dialog_btn.bind("<Button-1>", lambda e: on_dialog_close())

        def reset_hotkey():
            if recording_state["is_recording"]:
                return
            if self.hotkey_manager.reset_to_default():
                display_txt = self.hotkey_manager.get_display_text()
                # 重設後恢復一般按鈕底色，避免與外層區塊融合而看不到按鈕邊界。
                record_btn.config(text=display_txt, fg=self.palette["accent"], bg=self.palette["surface"])
                self._register_theme_widget(dialog, record_btn, "surface", "accent")
                show_tip("✓ 已重設為預設 (CTRL+ALT+V)", "success")
                schedule_tip_reset()

                self.status_label.config(text=display_txt)

        def cancel_recording():
            if not recording_state["is_recording"]:
                return
            recording_state["is_recording"] = False
            recording_state["recorded_keys"].clear()
            if recording_state["pynput_listener"]:
                try:
                    recording_state["pynput_listener"].stop()
                except Exception:
                    pass
                recording_state["pynput_listener"] = None
            self.hotkey_manager._start_listener()
            record_btn.config(
                text=self.hotkey_manager.get_display_text(),
                fg=self.palette["accent"], bg=self.palette["surface"]
            )
            self._register_theme_widget(dialog, record_btn, "surface", "accent")
            show_tip("已取消設定", "muted")
            schedule_tip_reset()

        def start_recording():
            if recording_state["is_recording"]:
                cancel_recording()
                return

            recording_state["is_recording"] = True
            recording_state["recorded_keys"].clear()
            record_btn.config(text="請按下組合鍵...", fg=self.palette["warning"], bg=self.palette["mic_active"])
            self._register_theme_widget(dialog, record_btn, "mic_active", "warning")
            if tip_message_timer["id"] is not None:
                dialog.after_cancel(tip_message_timer["id"])
                tip_message_timer["id"] = None
            show_tip("按下所有按鍵後，全部放開即儲存", "warning")

            def parse_key(key):
                if isinstance(key, Key):
                    name = key.name
                    if "ctrl" in name: return "<ctrl>"
                    if "alt" in name: return "<alt>"
                    if "shift" in name: return "<shift>"
                    if "cmd" in name or "win" in name: return "<cmd>"
                    return f"<{name}>"
                else:
                    if hasattr(key, 'vk') and key.vk:
                        vk = key.vk
                        if 48 <= vk <= 57: return chr(vk)
                        if 96 <= vk <= 105: return str(vk - 96)
                        if 65 <= vk <= 90: return chr(vk).lower()

                        symbol_vk_map = {
                            186: ';', 187: '=', 188: ',', 189: '-', 190: '.', 191: '/',
                            192: '`', 219: '[', 220: '\\', 221: ']', 222: "'"
                        }
                        if vk in symbol_vk_map: return symbol_vk_map[vk]

                        try:
                            char_code = ctypes.windll.user32.MapVirtualKeyW(vk, 2)
                            if char_code > 0: return chr(char_code).lower()
                        except Exception: pass

                    if hasattr(key, 'char') and key.char:
                        if ord(key.char) < 32: return chr(ord(key.char) + 96)
                        return key.char.lower()
                return None

            def on_press(key):
                k = parse_key(key)
                if k and k not in recording_state["recorded_keys"]:
                    recording_state["recorded_keys"].append(k)

            def finish_recording(key):
                if not dialog.winfo_exists():
                    return False
                if not recording_state["is_recording"]:
                    return False

                keys = recording_state["recorded_keys"]
                if keys:
                    mod_order = {"<ctrl>": 1, "<alt>": 2, "<shift>": 3, "<cmd>": 4}
                    modifiers = [k for k in keys if k in mod_order]
                    normal_keys = [k for k in keys if k not in mod_order]

                    modifiers.sort(key=lambda x: mod_order.get(x, 99))
                    normal_keys.sort()

                    final_keys = modifiers + normal_keys
                    new_hotkey_str = "+".join(final_keys)

                    recording_state["is_recording"] = False
                    if recording_state["pynput_listener"]:
                        recording_state["pynput_listener"].stop()

                    if self.hotkey_manager.update_hotkey(new_hotkey_str):
                        display_txt = self.hotkey_manager.get_display_text()
                        record_btn.config(text=display_txt, fg=self.palette["success"], bg=self.palette["surface"])

                        self._register_theme_widget(dialog, record_btn, "surface", "success")
                        show_tip("✓ 設定成功！", "success")
                        schedule_tip_reset()
                        self.status_label.config(text=display_txt)
                    else:
                        record_btn.config(text="錯誤", fg=self.palette["error"], bg=self.palette["surface"])
                        self._register_theme_widget(dialog, record_btn, "surface", "error")
                        show_tip("不支援的組合，請重試", "error")
                        self.hotkey_manager._start_listener()

                return False

            def on_release(key):
                # pynput 回呼來自背景執行緒，元件更新交回 Tk 事件迴圈。
                try:
                    self.root.after(0, lambda: finish_recording(key))
                except (tk.TclError, RuntimeError):
                    pass
                return False

            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            recording_state["pynput_listener"] = listener
            listener.start()

        record_btn.config(command=start_recording)

        clip_var = tk.BooleanVar(value=self.app.copy_to_clipboard)
        options_section = tk.Frame(dialog, bg=COLOR_BG)
        options_section.pack(fill="x", padx=24, pady=(0, 8))
        tk.Label(
            options_section, text="輸入選項", font=("Microsoft JhengHei UI", 9, "bold"),
            bg=COLOR_BG, fg="#f2f2f2", anchor="w"
        ).pack(fill="x", pady=(0, 3))
        cb = ToggleSwitch(
            options_section, text="辨識成功後自動複製到剪貼簿",
            variable=clip_var, palette=self.palette,
            command=lambda: self.app.set_copy_to_clipboard(clip_var.get())
        )
        cb.pack(fill="x")

        appearance = tk.Frame(dialog, bg=self.palette["bg"])
        appearance.pack(fill="x", padx=24, pady=(8, 0))
        tk.Label(appearance, text="外觀", bg=self.palette["bg"],
                 fg=self.palette["text"], font=("Microsoft JhengHei UI", 9, "bold")).pack(anchor="w", pady=(0, 6))
        choices = tk.Frame(appearance, bg=self.palette["bg"])
        choices.pack(fill="x")
        self._theme_buttons = {}
        dark_button = RoundedButton(choices, text="深色", width=145, height=36,
                                    command=lambda: self.app.set_theme("dark"))
        light_button = RoundedButton(choices, text="淺色", width=145, height=36,
                                     command=lambda: self.app.set_theme("light"))
        for value, button in (("dark", dark_button), ("light", light_button)):
            button.pack(side="left", padx=(0, 8))
            self._theme_buttons[value] = button

        footer = tk.Frame(dialog, bg=COLOR_BG, height=54)
        footer.pack(fill="x", padx=24, pady=(12, 22))
        footer.pack_propagate(False)
        reset_btn = RoundedButton(
            footer,
            text="重設快捷鍵",
            bg=COLOR_SURFACE,
            fg=COLOR_ICON, 
            width=150, height=34, radius=10, command=reset_hotkey
        )
        reset_btn.pack(side="left", anchor="center")
        reset_btn.bind("<Enter>", lambda e: reset_btn.config(bg=COLOR_ACCENT, fg="white"))
        reset_btn.bind("<Leave>", lambda e: reset_btn.config(bg=COLOR_SURFACE, fg=COLOR_ICON))
        tk.Label(
            footer, text="預設組合：Ctrl + Alt + V",
            font=("Microsoft JhengHei UI", 8), bg=COLOR_BG, fg=COLOR_MUTED
        ).pack(side="left", padx=(10, 0))
        self._register_theme_subtree(dialog, titlebar, "surface", "text")
        self._register_theme_subtree(dialog, header, "bg", "text")
        self._register_theme_subtree(dialog, hotkey_section, "mic_bg", "text")
        self._register_theme_widget(dialog, record_btn, "surface", "accent")
        self._register_theme_widget(dialog, tip_label, "mic_bg", "muted")
        self._register_theme_subtree(dialog, options_section, "bg", "text")
        self._register_theme_subtree(dialog, appearance, "bg", "text")
        self._register_theme_subtree(dialog, footer, "bg", "text")
        self._register_theme_widget(dialog, reset_btn, "surface", "text")
        self._hover_config(record_btn, "accent", "text", "surface", "accent")
        self._hover_config(reset_btn, "accent", "text", "surface", "text")
        self._hover_config(close_dialog_btn, "error", "text", "surface", "muted")
        dialog.bind("<Destroy>", lambda event: self._forget_theme_window(dialog) if event.widget is dialog else None, add="+")
        dialog_height = 540
        dialog.geometry(f"{dialog_width}x{dialog_height}")
        self._apply_theme_widgets()
        dialog.update_idletasks()
        _apply_rounded_window(dialog, radius=18)
        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()

    def _show_help(self):
        if self.help_dialog is not None:
            try:
                if self.help_dialog.winfo_exists():
                    self.help_dialog.deiconify()
                    self.help_dialog.lift()
                    self.help_dialog.focus_force()
                    return
            except tk.TclError:
                self.help_dialog = None
        help_dialog = tk.Toplevel(self.root)
        help_dialog._theme_owner = self
        self.help_dialog = help_dialog
        self._register_theme_widget(help_dialog, help_dialog, "bg")
        help_dialog.title("使用說明")
        
        dialog_width = 380
        dialog_height = 356
        help_dialog.configure(bg=self.palette["bg"])
        help_dialog.resizable(False, False)
        help_dialog.attributes("-topmost", True)
        help_dialog.transient(self.root)
        help_dialog.overrideredirect(True)
        help_dialog.configure(bg=self.palette["bg"], highlightthickness=0)

        titlebar = tk.Frame(help_dialog, bg=COLOR_SURFACE, height=38)
        titlebar.pack(fill="x", side="top")
        titlebar.pack_propagate(False)
        tk.Label(
            titlebar, text="使用說明", font=("Microsoft JhengHei UI", 10, "bold"),
            bg=COLOR_SURFACE, fg="#f2f2f2", anchor="w"
        ).pack(side="left", padx=16)
        close_help_btn = tk.Label(
            titlebar, text="✕", font=("Segoe UI Symbol", 10),
            bg=COLOR_SURFACE, fg=COLOR_MUTED, cursor="hand2", padx=12
        )
        close_help_btn.pack(side="right", fill="y")
        close_help_btn.bind("<Enter>", lambda e: close_help_btn.config(bg="#c42b3c", fg="white"))
        close_help_btn.bind("<Leave>", lambda e: close_help_btn.config(bg=COLOR_SURFACE, fg=COLOR_MUTED))

        drag_state = {"x": 0, "y": 0}
        def start_help_drag(event):
            drag_state["x"], drag_state["y"] = event.x_root - help_dialog.winfo_x(), event.y_root - help_dialog.winfo_y()
        def drag_help(event):
            help_dialog.geometry(f"+{event.x_root - drag_state['x']}+{event.y_root - drag_state['y']}")
        titlebar.bind("<ButtonPress-1>", start_help_drag)
        titlebar.bind("<B1-Motion>", drag_help)

        screen_width = help_dialog.winfo_screenwidth()
        screen_height = help_dialog.winfo_screenheight()
        center_x = int((screen_width - dialog_width) / 2)
        center_y = int((screen_height - dialog_height) / 2)
        help_dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        header = tk.Frame(help_dialog, bg=COLOR_BG)
        header.pack(fill="x", padx=24, pady=(20, 12))
        tk.Label(
            header, text="使用說明", font=("Microsoft JhengHei UI", 16, "bold"),
            bg=COLOR_BG, fg="#f2f2f2", anchor="w"
        ).pack(fill="x")
        tk.Label(
            header, text="用快捷鍵或麥克風按鈕快速輸入粵語", font=("Microsoft JhengHei UI", 9),
            bg=COLOR_BG, fg=COLOR_MUTED, anchor="w"
        ).pack(fill="x", pady=(3, 0))

        current_hotkey = self.hotkey_manager.get_display_text()
        copy_note = "並複製至剪貼簿" if self.app.copy_to_clipboard else ""
        steps = tk.Frame(help_dialog, bg=COLOR_SURFACE)
        steps.pack(fill="x", padx=24, pady=(0, 16))
        instructions = [
            ("01", f"按下 {current_hotkey} 或點擊麥克風"),
            ("02", "對著麥克風說廣東話"),
            ("03", f"文字會自動輸入到游標位置{copy_note}"),
            ("04", "按 ✕ 隱藏浮窗，可從系統托盤恢復"),
        ]
        for index, (number, text) in enumerate(instructions):
            row = tk.Frame(steps, bg=COLOR_SURFACE)
            row.pack(fill="x", padx=14, pady=(11 if index == 0 else 4, 4 if index < len(instructions) - 1 else 11))
            tk.Label(row, text=number, font=("Segoe UI", 8, "bold"), bg=COLOR_ACCENT, fg="white", width=4).pack(side="left")
            tk.Label(row, text=text, font=("Microsoft JhengHei UI", 9), bg=COLOR_SURFACE, fg="#d8d8d8", anchor="w").pack(side="left", padx=10)

        footer = tk.Frame(help_dialog, bg=COLOR_BG)
        footer.pack(fill="x", padx=24, pady=(0, 18))
        def close_help():
            self.help_dialog = None
            self._forget_theme_window(help_dialog)
            help_dialog.destroy()

        ok_btn = RoundedButton(
            footer,
            text="關閉",
            bg=COLOR_SURFACE,
            fg=COLOR_ACCENT, 
            width=120, height=36, radius=10, command=close_help
        )
        ok_btn.pack(anchor="center")
        ok_btn.bind("<Enter>", lambda e: ok_btn.config(bg=COLOR_ACCENT, fg="white"))
        ok_btn.bind("<Leave>", lambda e: ok_btn.config(bg=COLOR_SURFACE, fg=COLOR_ACCENT))
        close_help_btn.bind("<Button-1>", lambda e: close_help())
        self._register_theme_subtree(help_dialog, titlebar, "surface", "text")
        self._register_theme_subtree(help_dialog, header, "bg", "text")
        self._register_theme_subtree(help_dialog, steps, "surface", "text")
        self._register_theme_subtree(help_dialog, footer, "bg", "text")
        for child in steps.winfo_children():
            for index, label in enumerate(child.winfo_children()):
                self._register_theme_widget(help_dialog, label, "accent" if index == 0 else "surface", "text")
        self._register_theme_widget(help_dialog, ok_btn, "surface", "accent")
        self._hover_config(ok_btn, "accent", "text", "surface", "accent")
        self._hover_config(close_help_btn, "error", "text", "surface", "muted")
        help_dialog.protocol("WM_DELETE_WINDOW", close_help)
        help_dialog.bind("<Destroy>", lambda event: self._forget_theme_window(help_dialog) if event.widget is help_dialog else None, add="+")
        help_dialog.update_idletasks()
        _apply_rounded_window(help_dialog, radius=18)
        help_dialog.deiconify()
        help_dialog.lift()
        help_dialog.focus_force()

    def toggle_ui(self):
        if self.is_visible:
            self.hide_ui()
        else:
            self.show_ui()

    def show_ui(self):
        if self.root:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.is_visible = True

    def hide_ui(self):
        if self.root:
            self.root.withdraw()
            self.is_visible = False

    def destroy_app(self):
        if self.on_close_callback:
            self.on_close_callback()
        if self.root:
            self._theme_bindings.clear()
            self.root.quit()
            self.root.destroy()

    def _prevent_focus(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE)
        except Exception:
            pass

    def _start_drag(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _do_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._drag_start_x)
        y = self.root.winfo_y() + (event.y - self._drag_start_y)
        self.root.geometry(f"+{x}+{y}")

    def _check_queue(self):
        try:
            while not self.ui_queue.empty():
                item = self.ui_queue.get_nowait()

                # 處理複製到剪貼簿的要求
                if isinstance(item, tuple) and item[0] == "CLIPBOARD":
                    text_to_copy = item[1]
                    try:
                        self.root.clipboard_clear()
                        self.root.clipboard_append(text_to_copy)
                        self.root.update()
                    except Exception as clip_err:
                        print(f"[剪貼簿錯誤]: {clip_err}")
                    continue

                state, msg, color_role = item
                palette = self.palette
                
                if msg:
                    self._status_role = color_role if color_role in palette else "text"
                    self._register_theme_widget(self.root, self.status_label, "bg", self._status_role)
                    color = palette[color_role] if color_role in palette else palette["text"]
                    self.status_label.config(text=msg, fg=color)
                
                if state == "LISTENING":
                    self._draw_mic_button(active=True)
                elif state == "IDLE":
                    self._draw_mic_button(active=False)
                    
        except Exception:
            pass
            
        if self.root:
            self.root.after(50, self._check_queue)

class VoiceInputApp:
    def __init__(self, ui_queue, hotkey_manager):
        self.ui_queue = ui_queue
        self.hotkey_manager = hotkey_manager
        self.kb_controller = KeyboardController()
        self.driver = None
        config = load_config()
        self.theme = config["theme"]
        self.copy_to_clipboard = config["copy_to_clipboard"]
        self.ui = None
        self._initialize_driver()

    def _initialize_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--app=https://www.google.com.hk")
        chrome_options.add_argument("--window-position=-32000,-32000")
        chrome_options.add_argument("--window-size=1,1")

        # 強制語音鎖定廣東話 zh-HK
        chrome_options.add_argument("--lang=zh-HK")
        chrome_options.add_experimental_option("prefs", {
            "intl.accept_languages": "zh-HK,zh",
            "profile.default_content_setting_values.media_stream_mic": 1
        })

        chrome_options.add_argument("--use-fake-ui-for-media-stream")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])

        # 記憶體安全優化參數
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--renderer-process-limit=1")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--no-default-browser-check")

        user_data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'Google', 'Chrome', 'User Data VoiceAppFix')
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self._hide_chrome_window()
            self._setup_permissions()
        except Exception as e:
            print(f"[錯誤] Chrome 驅動初始化失敗: {e}")
            raise

    def _setup_permissions(self):
        """設置麥克風權限"""
        try:
            self.driver.execute_cdp_cmd("Browser.grantPermissions", {
                "origin": "https://www.google.com.hk",
                "permissions": ["audioCapture"]
            })
            self.driver.execute_cdp_cmd("Browser.grantPermissions", {
                "origin": "https://www.google.com",
                "permissions": ["audioCapture"]
            })
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
        except Exception as e:
            print(f"[警告] 權限設置失敗: {e}")

        self.wait = WebDriverWait(self.driver, 10)
        self.is_processing = False
        self.stop_event = threading.Event()
        self.reset_timer = None

    def _hide_chrome_window(self):
        try:
            hwnd = ctypes.windll.user32.FindWindowW(None, self.driver.title)
            if not hwnd:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception as e:
            print(f"[提示] 隱藏視窗失敗: {e}")

    def quit(self):
        if self.reset_timer:
            self.reset_timer.cancel()
        try:
            if self.driver:
                self.driver.quit()
        except Exception as e:
            print(f"[警告] 關閉 Chrome 時發生例外: {e}")

    def set_copy_to_clipboard(self, value):
        self.copy_to_clipboard = bool(value)
        save_config({"copy_to_clipboard": self.copy_to_clipboard})

    def set_theme(self, theme):
        if not isinstance(theme, str) or theme not in THEME_PALETTES:
            return False
        self.theme = theme
        save_config({"theme": theme})
        ui = self.ui
        if ui and ui.root:
            ui.root.after(0, lambda: ui.apply_theme(theme))
        return True

    def _reset_status_message(self):
        self.ui_queue.put(("IDLE", self.hotkey_manager.get_display_text(), "muted"))

    SPEECH_JS = r"""
    window.__voiceResult = { done: false, transcript: '', error: '' };
    (function () {
      var rec = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
      rec.lang = 'zh-HK';
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.onresult = function (e) {
        var t = '';
        for (var i = 0; i < e.results.length; i++) {
          if (e.results[i].length) t += e.results[i][0].transcript;
        }
        window.__voiceResult = { done: true, transcript: t, error: '' };
      };
      rec.onerror = function (e) {
        window.__voiceResult = { done: true, transcript: '', error: e.error };
      };
      rec.onend = function () {
        if (!window.__voiceResult.done) {
          window.__voiceResult = { done: true, transcript: '', error: 'no-speech' };
        }
      };
      rec.start();
    })();
    """

    def _capture_speech(self):
        """直接呼叫 webkitSpeechRecognition，事件驅動取得辨識文字（最多約 12 秒）。"""
        self.driver.execute_script(self.SPEECH_JS)
        result = {"done": False, "transcript": "", "error": ""}
        for _ in range(60):
            if self.stop_event.is_set():
                return "", "aborted"
            time.sleep(0.2)
            result = self.driver.execute_script("return window.__voiceResult;")
            if result.get("done"):
                break
        return result.get("transcript", ""), result.get("error", "")

    def _process_speech(self):
        if self.reset_timer:
            self.reset_timer.cancel()

        try:
            play_sound("start")
            self.ui_queue.put(("LISTENING", "聆聽中...", "accent"))

            self.driver.get("https://www.google.com.hk/webhp?hl=zh-HK")

            if self.stop_event.is_set():
                return

            recognized_text, error = self._capture_speech()
            recognized_text = recognized_text.strip()

            if recognized_text:
                play_sound("success")

                if self.copy_to_clipboard:
                    self.ui_queue.put(("CLIPBOARD", recognized_text))

                display_text = recognized_text if len(recognized_text) <= 12 else recognized_text[:12] + "..."

                self.ui_queue.put(("IDLE", f"✨ {display_text}", "success"))

                self.kb_controller.type(recognized_text)
            elif error == "no-speech":
                play_sound("fail")
                self.ui_queue.put(("IDLE", "⚠️ 未聽清", "warning"))
            elif error in ("not-allowed", "service-not-allowed"):
                play_sound("fail")
                self.ui_queue.put(("IDLE", "❌ 麥克風權限被拒", "error"))
            elif error == "network":
                play_sound("fail")
                self.ui_queue.put(("IDLE", "❌ 無法連線識別", "error"))
            elif error == "aborted":
                self.ui_queue.put(("IDLE", self.hotkey_manager.get_display_text(), "muted"))
            else:
                play_sound("fail")
                self.ui_queue.put(("IDLE", "⚠️ 識別失敗", "warning"))

        except Exception as e:
            print(f"[系統提示]: {e}")
            self.ui_queue.put(("IDLE", self.hotkey_manager.get_display_text(), "muted"))
        finally:
            self.is_processing = False
            self.stop_event.clear()

            self.reset_timer = threading.Timer(3.0, self._reset_status_message)
            self.reset_timer.start()

    def _ensure_driver_alive(self):
        """檢查 Chrome 程序是否存活，若崩潰自動重啟"""
        if not self.driver:
            return False
        try:
            self.driver.execute_script("return 1")
            return True
        except Exception as e:
            print(f"[警告] Chrome 程序異常: {e}，重啟中...")
            try:
                self.driver.quit()
            except Exception:
                pass
            try:
                self._initialize_driver()
                return True
            except Exception as e:
                print(f"[錯誤] Chrome 重啟失敗: {e}")
                self.ui_queue.put(("IDLE", "❌ Chrome 崩潰", "error"))

                return False

    def trigger_speech(self):
        if not self._ensure_driver_alive():
            return

        if self.is_processing:
            play_sound("fail")
            self.stop_event.set()
            return

        self.is_processing = True
        self.stop_event.clear()
        threading.Thread(target=self._process_speech, daemon=True).start()

def setup_tray_icon(input_bar, tray_icon_holder):
    def on_toggle_click(icon, item):
        input_bar.root.after(0, input_bar.toggle_ui)

    def on_exit_click(icon, item):
        icon.stop()
        input_bar.root.after(0, input_bar.destroy_app)

    menu = pystray.Menu(
        pystray.MenuItem("顯示/隱藏卡片", on_toggle_click, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出程式", on_exit_click)
    )

    icon = pystray.Icon(
        "CantoneseVoiceInput",
        create_tray_icon_image(),
        "粵語語音輸入法",
        menu
    )
    tray_icon_holder['icon'] = icon
    icon.run()

if __name__ == "__main__":
    try:
        ui_queue = queue.Queue()
        
        hotkey_manager = DynamicHotkeyManager(action_callback=lambda: app.trigger_speech())
        
        app = VoiceInputApp(ui_queue, hotkey_manager)
        
        input_bar = CardVoiceUI(
            ui_queue,
            on_mic_click_callback=app.trigger_speech,
            hotkey_manager=hotkey_manager,
            app=app,
            on_close_callback=app.quit
        )

        tray_icon_holder = {}
        tray_thread = threading.Thread(
            target=setup_tray_icon, 
            args=(input_bar, tray_icon_holder), 
            daemon=True
        )
        tray_thread.start()

        input_bar.start()

    except Exception as e:
        err_msg = traceback.format_exc()
        root_err = tk.Tk()
        root_err.withdraw()
        messagebox.showerror("啟動失敗 (Crash Log)", f"程式發生致命錯誤：\n\n{err_msg}")
        root_err.destroy()
