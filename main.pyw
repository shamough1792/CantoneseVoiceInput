import time
import re
import os
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
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

import pystray
from PIL import Image, ImageDraw

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000

DEFAULT_CONFIG = {"copy_to_clipboard": False}
CONFIG_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'CantoneseVoiceInput')

def load_config():
    try:
        with open(os.path.join(CONFIG_DIR, 'config.json'), 'r', encoding='utf-8') as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    except Exception:
        return dict(DEFAULT_CONFIG)

def save_config(config):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(os.path.join(CONFIG_DIR, 'config.json'), 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[設定] 無法儲存設定檔: {e}")


# 主題配色定義 (Windows 風格深色介面)
COLOR_BG = "#1f1f1f"         # 主背景深灰
COLOR_BORDER = "#3c3c3c"     # 邊框與分割線
COLOR_ACCENT = "#0078d4"     # Windows 藍色高亮
COLOR_ICON = "#c8c8c8"       # 圖示與文字預設灰色
COLOR_MIC_BG = "#2a2a2a"     # 麥克風底圈
COLOR_MIC_ACTIVE = "#333333"  # 錄音中麥克風底圈

def play_sound(sound_type="start"):
    """發出輕柔自然的原生系統通知聲"""
    def _play():
        try:
            if sound_type == "start":
                winsound.PlaySound("Notification.Default", winsound.SND_ALIAS | winsound.SND_ASYNC)
            elif sound_type == "success":
                winsound.PlaySound("SystemNotification", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()

def is_garbage_token(text):
    return bool(len(text) > 30 and re.match(r'^[A-Za-z0-9_\-]+$', text))

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

class CardVoiceUI:
    def __init__(self, ui_queue, on_mic_click_callback, hotkey_manager, app, on_close_callback=None):
        self.ui_queue = ui_queue
        self.on_mic_click = on_mic_click_callback
        self.hotkey_manager = hotkey_manager
        self.app = app
        self.on_close_callback = on_close_callback
        self.root = None
        self.mic_btn_canvas = None
        self.status_label = None
        
        self.is_visible = True
        self._drag_start_x = 0
        self._drag_start_y = 0

    def start(self):
        self.root = tk.Tk()
        self.root.title("粵語語音輸入法")
        
        self.root.attributes("-toolwindow", True)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        TRANS_COLOR = "#000001"

        self.root.config(bg=TRANS_COLOR)
        self.root.wm_attributes("-transparentcolor", TRANS_COLOR)
        self.root.attributes("-alpha", 0.82)

        self.root.protocol("WM_DELETE_WINDOW", self.hide_ui)

        self.width = 192
        self.height = 112

        self.main_canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=TRANS_COLOR,
            highlightthickness=0
        )
        self.main_canvas.pack()

        self._draw_round_rect(0, 0, self.width, self.height, radius=15, fill=COLOR_BG, outline=COLOR_BORDER)

        top_frame = tk.Frame(self.root, bg=COLOR_BG)
        top_frame.place(x=8, y=6, width=self.width-16, height=20)

        handle_canvas = tk.Canvas(top_frame, width=36, height=6, bg=COLOR_BG, highlightthickness=0)
        handle_canvas.pack(side="top", pady=1)
        handle_canvas.create_rectangle(2, 1, 34, 5, fill="#5a5a5a", outline="")


        close_btn = tk.Label(
            top_frame,
            text="✕",
            font=("Microsoft JhengHei UI", 9),
            bg=COLOR_BG,
            fg=COLOR_ICON,
            cursor="hand2"
        )
        close_btn.place(x=self.width-34, y=-1, width=18, height=18)
        close_btn.bind("<Button-1>", lambda e: self.hide_ui())
        close_btn.bind("<Enter>", lambda e: close_btn.config(fg="#d13438"))

        close_btn.bind("<Leave>", lambda e: close_btn.config(fg=COLOR_ICON))

        mid_frame = tk.Frame(self.root, bg=COLOR_BG)
        mid_frame.place(x=8, y=27, width=self.width-16, height=52)

        setting_btn = tk.Label(mid_frame, text="⚙", font=("Segoe UI Symbol", 12), bg=COLOR_BG, fg=COLOR_ICON, cursor="hand2")
        setting_btn.pack(side="left", padx=(8, 8))
        setting_btn.bind("<Button-1>", lambda e: self._open_settings_dialog())
        setting_btn.bind("<Enter>", lambda e: setting_btn.config(fg=COLOR_ACCENT))
        setting_btn.bind("<Leave>", lambda e: setting_btn.config(fg=COLOR_ICON))

        self.mic_btn_canvas = tk.Canvas(mid_frame, width=50, height=50, bg=COLOR_BG, highlightthickness=0, cursor="hand2")
        self.mic_btn_canvas.pack(side="left", expand=True)
        self._draw_mic_button(active=False)
        self.mic_btn_canvas.bind("<Button-1>", lambda e: self.on_mic_click())

        help_btn = tk.Label(mid_frame, text="❓", font=("Segoe UI Symbol", 10), bg=COLOR_BG, fg=COLOR_ICON, cursor="hand2")
        help_btn.pack(side="right", padx=(8, 8))
        help_btn.bind("<Button-1>", lambda e: self._show_help())
        help_btn.bind("<Enter>", lambda e: help_btn.config(fg=COLOR_ACCENT))
        help_btn.bind("<Leave>", lambda e: help_btn.config(fg=COLOR_ICON))

        self.status_label = tk.Label(
            self.root,
            text=self.hotkey_manager.get_display_text(),
            font=("Microsoft JhengHei UI", 8),
            bg=COLOR_BG,
            fg=COLOR_ICON,
            anchor="w"
        )
        self.status_label.place(x=10, y=83, width=self.width-20, height=18)

        for widget in [self.main_canvas, handle_canvas, top_frame, mid_frame]:
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._do_drag)

        self.root.update_idletasks()

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_pos = screen_width - self.width - 20
        y_pos = screen_height - self.height - 60
        self.root.geometry(f"{self.width}x{self.height}+{x_pos}+{y_pos}")

        self._prevent_focus()

        self.root.after(50, self._check_queue)
        self.root.mainloop()

    def _draw_round_rect(self, x1, y1, x2, y2, radius=14, **kwargs):
        points = [x1+radius, y1,
                  x2-radius, y1,
                  x2, y1,
                  x2, y1+radius,
                  x2, y2-radius,
                  x2, y2,
                  x2-radius, y2,
                  x1+radius, y2,
                  x1, y2,
                  x1, y2-radius,
                  x1, y1+radius,
                  x1, y1]
        return self.main_canvas.create_polygon(points, smooth=True, **kwargs)

    def _draw_mic_button(self, active=False):
        self.mic_btn_canvas.delete("all")
        bg_circle_color = COLOR_MIC_BG if not active else COLOR_MIC_ACTIVE
        icon_color = COLOR_ACCENT

        border_color = COLOR_ACCENT if active else COLOR_BORDER
        border_width = 2 if active else 1

        self.mic_btn_canvas.create_oval(
            3, 3, 47, 47,
            fill=bg_circle_color,
            outline=border_color,
            width=border_width
        )

        mic_symbol = "🎙️" if not active else "⏹️"
        self.mic_btn_canvas.create_text(25, 25, text=mic_symbol, font=("Segoe UI Emoji", 13), fill=icon_color)

    def _open_settings_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("設定快捷鍵")
        
        dialog_width = 286
        dialog_height = 214
        dialog.configure(bg=COLOR_BG)
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)

        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        center_x = int((screen_width - dialog_width) / 2)
        center_y = int((screen_height - dialog_height) / 2)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        tk.Label(dialog, text="目前的快捷鍵：", font=("Microsoft JhengHei UI", 9), bg=COLOR_BG, fg=COLOR_ICON).pack(pady=(12, 2))

        record_btn = tk.Button(
            dialog, 
            text=self.hotkey_manager.get_display_text(), 
            font=("Segoe UI", 10, "bold"), 
            bg=COLOR_MIC_BG, 
            fg=COLOR_ACCENT, 
            activebackground=COLOR_MIC_ACTIVE,
            activeforeground=COLOR_ACCENT,
            bd=1, 
            relief="solid",
            width=22,
            cursor="hand2"
        )
        record_btn.pack(pady=4, ipady=4)

        tip_label = tk.Label(dialog, text="點擊上方按鈕，按下新快捷鍵組合", font=("Microsoft JhengHei UI", 8), bg=COLOR_BG, fg=COLOR_ICON)
        tip_label.pack(pady=(2, 6))

        recording_state = {"is_recording": False, "recorded_keys": [], "pynput_listener": None}

        self.hotkey_manager.stop_listener()

        def on_dialog_close():
            if recording_state["pynput_listener"]:
                try:
                    recording_state["pynput_listener"].stop()
                except Exception:
                    pass
            self.hotkey_manager._start_listener()
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

        def reset_hotkey():
            if recording_state["is_recording"]:
                return
            if self.hotkey_manager.reset_to_default():
                display_txt = self.hotkey_manager.get_display_text()
                record_btn.config(text=display_txt, fg=COLOR_ACCENT, bg=COLOR_MIC_BG)
                tip_label.config(text="✓ 已重設為預設 (CTRL+ALT+V)", fg="#107c10")

                self.status_label.config(text=display_txt)

        def start_recording():
            if recording_state["is_recording"]:
                return

            recording_state["is_recording"] = True
            recording_state["recorded_keys"].clear()
            record_btn.config(text="請按下組合鍵...", fg="#c19c00", bg=COLOR_MIC_ACTIVE)

            tip_label.config(text="按下所有按鍵後，全部放開即儲存", fg="#FF9500")

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

            def on_release(key):
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
                        record_btn.config(text=display_txt, fg="#107c10", bg=COLOR_MIC_BG)

                        tip_label.config(text="✓ 設定成功！", fg="#34C759")
                        self.status_label.config(text=display_txt)
                    else:
                        record_btn.config(text="錯誤", fg="#FF3B30", bg=COLOR_MIC_BG)
                        tip_label.config(text="不支援的組合，請重試", fg="#FF3B30")
                        self.hotkey_manager._start_listener()

                return False

            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            recording_state["pynput_listener"] = listener
            listener.start()

        record_btn.config(command=start_recording)

        clip_var = tk.BooleanVar(value=self.app.copy_to_clipboard)
        cb = tk.Checkbutton(
            dialog, text="辨識後自動複製到剪貼簿",
            variable=clip_var, bg=COLOR_BG, fg=COLOR_ICON,
            activebackground=COLOR_BG, activeforeground=COLOR_ICON,
            selectcolor=COLOR_MIC_BG, font=("Microsoft JhengHei UI", 9),
            command=lambda: self.app.set_copy_to_clipboard(clip_var.get())
        )
        cb.pack(pady=(2, 2))

        reset_btn = tk.Button(
            dialog, 
            text="重設為預設值", 
            font=("Microsoft JhengHei UI", 8), 
            bg=COLOR_BG, 
            fg=COLOR_ICON, 
            activebackground=COLOR_BG,
            activeforeground="#d13438",

            bd=0, 
            cursor="hand2",
            command=reset_hotkey
        )
        reset_btn.pack(pady=(0, 4))

    def _show_help(self):
        help_dialog = tk.Toplevel(self.root)
        help_dialog.title("使用說明")
        
        dialog_width = 300
        dialog_height = 200
        help_dialog.configure(bg=COLOR_BG)
        help_dialog.resizable(False, False)
        help_dialog.attributes("-topmost", True)

        screen_width = help_dialog.winfo_screenwidth()
        screen_height = help_dialog.winfo_screenheight()
        center_x = int((screen_width - dialog_width) / 2)
        center_y = int((screen_height - dialog_height) / 2)
        help_dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        title_label = tk.Label(
            help_dialog, 
            text="粵語語音輸入法指南", 
            font=("Microsoft JhengHei UI", 10, "bold"), 
            bg=COLOR_BG, 
            fg=COLOR_ACCENT
        )
        title_label.pack(pady=(15, 10))

        current_hotkey = self.hotkey_manager.get_display_text()
        copy_note = "並複製至剪貼簿" if self.app.copy_to_clipboard else ""
        help_text = (
            f"1. 按下快捷鍵 ({current_hotkey}) 開始錄音\n"
            "2. 對著麥克風講廣東話\n"
            f"3. 識別後將自動輸入至游標位置{copy_note}\n"
            "4. 點擊 ✕ 可隱藏浮窗，由右下角托盤重啟"
        )
        
        content_label = tk.Label(
            help_dialog, 
            text=help_text, 
            font=("Microsoft JhengHei UI", 9), 
            bg=COLOR_BG, 
            fg=COLOR_ICON,
            justify="left"
        )
        content_label.pack(padx=20, pady=(0, 15), anchor="w")

        ok_btn = tk.Button(
            help_dialog, 
            text="了解", 
            font=("Microsoft JhengHei UI", 9), 
            bg=COLOR_MIC_BG, 
            fg=COLOR_ACCENT, 
            activebackground=COLOR_MIC_ACTIVE,
            activeforeground=COLOR_ACCENT,
            bd=1, 
            relief="solid",
            width=10,
            cursor="hand2",
            command=help_dialog.destroy
        )
        ok_btn.pack(pady=(0, 15))

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

                state, msg, color = item
                
                if msg:
                    self.status_label.config(text=msg, fg=color if color else COLOR_ICON)
                
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
        self.copy_to_clipboard = load_config().get("copy_to_clipboard", False)
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

    def _reset_status_message(self):
        self.ui_queue.put(("IDLE", self.hotkey_manager.get_display_text(), COLOR_ICON))

    def _get_current_text(self):
        try:
            search_box = self.driver.find_element(By.NAME, "q")
            val = search_box.get_attribute("value").strip()
            if val and not is_garbage_token(val):
                return val
        except Exception:
            pass
        return ""

    def _process_speech(self):
        if self.reset_timer:
            self.reset_timer.cancel()

        try:
            play_sound("start")
            self.ui_queue.put(("LISTENING", "聆聽中...", COLOR_ACCENT))

            self.driver.get("https://www.google.com.hk/webhp?hl=zh-HK")

            if self.stop_event.is_set():
                return

            mic_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//*[@aria-label='語音搜尋' or @aria-label='Search by voice']"))
            )
            mic_button.click()
            
            recognized_text = ""
            
            for _ in range(30):
                if self.stop_event.is_set():
                    recognized_text = self._get_current_text()
                    break

                time.sleep(0.5)
                
                current_val = self._get_current_text()
                if current_val:
                    recognized_text = current_val
                    break

            if not recognized_text:
                recognized_text = self._get_current_text()

            if recognized_text:
                play_sound("success")

                if self.copy_to_clipboard:
                    self.ui_queue.put(("CLIPBOARD", recognized_text))

                display_text = recognized_text if len(recognized_text) <= 12 else recognized_text[:12] + "..."

                self.ui_queue.put(("IDLE", f"✨ {display_text}", "#107c10"))

                self.kb_controller.type(recognized_text)
            else:
                self.ui_queue.put(("IDLE", "⚠️ 未聽清", "#c19c00"))


        except Exception as e:
            print(f"[系統提示]: {e}")
            self.ui_queue.put(("IDLE", self.hotkey_manager.get_display_text(), COLOR_ICON))
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
                self.ui_queue.put(("IDLE", "❌ Chrome 崩潰", "#d13438"))

                return False

    def trigger_speech(self):
        if not self._ensure_driver_alive():
            return

        if self.is_processing:
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