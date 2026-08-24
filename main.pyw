import time
import re
import os
import ctypes
import threading
import queue
import tkinter as tk
from tkinter import messagebox
from pynput import keyboard
from pynput.keyboard import Controller as KeyboardController, Key
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import pystray
from PIL import Image, ImageDraw

# 自動隱藏 CMD 主控台
hwnd_console = ctypes.windll.kernel32.GetConsoleWindow()
if hwnd_console:
    ctypes.windll.user32.ShowWindow(hwnd_console, 0)

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000

def is_garbage_token(text):
    return bool(len(text) > 30 and re.match(r'^[A-Za-z0-9_\-]+$', text))

def create_tray_icon_image():
    width, height = 32, 32
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse((2, 2, 30, 30), fill='#222224', outline='#55B2FF', width=2)
    dc.rectangle((13, 8, 19, 18), fill='#55B2FF')
    dc.arc((10, 12, 22, 22), 0, 180, fill='#55B2FF', width=2)
    dc.line((16, 22, 16, 26), fill='#55B2FF', width=2)
    dc.line((12, 26, 20, 26), fill='#55B2FF', width=2)
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
    def __init__(self, ui_queue, on_mic_click_callback, hotkey_manager, on_close_callback=None):
        self.ui_queue = ui_queue
        self.on_mic_click = on_mic_click_callback
        self.hotkey_manager = hotkey_manager
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
        BG_COLOR = "#222224"
        BORDER_COLOR = "#333336"

        self.root.config(bg=TRANS_COLOR)
        self.root.wm_attributes("-transparentcolor", TRANS_COLOR)
        self.root.attributes("-alpha", 0.96)

        self.root.protocol("WM_DELETE_WINDOW", self.hide_ui)

        self.width = 190
        self.height = 110

        self.main_canvas = tk.Canvas(
            self.root, 
            width=self.width, 
            height=self.height, 
            bg=TRANS_COLOR, 
            highlightthickness=0
        )
        self.main_canvas.pack()

        self._draw_round_rect(0, 0, self.width, self.height, radius=14, fill=BG_COLOR, outline=BORDER_COLOR)

        top_frame = tk.Frame(self.root, bg=BG_COLOR)
        top_frame.place(x=8, y=6, width=self.width-16, height=22)

        handle_canvas = tk.Canvas(top_frame, width=32, height=6, bg=BG_COLOR, highlightthickness=0)
        handle_canvas.pack(side="top", pady=2)
        handle_canvas.create_rectangle(0, 1, 32, 5, fill="#55555A", outline="")

        close_btn = tk.Label(
            top_frame, 
            text="✕", 
            font=("Microsoft JhengHei UI", 8), 
            bg="#2A2A2D", 
            fg="#AAAAAE",
            cursor="hand2"
        )
        close_btn.place(x=self.width-36, y=0, width=18, height=18)
        close_btn.bind("<Button-1>", lambda e: self.hide_ui())
        close_btn.bind("<Enter>", lambda e: close_btn.config(bg="#FF3B30", fg="#FFFFFF"))
        close_btn.bind("<Leave>", lambda e: close_btn.config(bg="#2A2A2D", fg="#AAAAAE"))

        mid_frame = tk.Frame(self.root, bg=BG_COLOR)
        mid_frame.place(x=8, y=28, width=self.width-16, height=50)

        setting_btn = tk.Label(mid_frame, text="⚙", font=("Segoe UI Symbol", 11), bg=BG_COLOR, fg="#8E8E93", cursor="hand2")
        setting_btn.pack(side="left", padx=10)
        setting_btn.bind("<Button-1>", lambda e: self._open_settings_dialog())
        setting_btn.bind("<Enter>", lambda e: setting_btn.config(fg="#FFFFFF"))
        setting_btn.bind("<Leave>", lambda e: setting_btn.config(fg="#8E8E93"))

        self.mic_btn_canvas = tk.Canvas(mid_frame, width=46, height=46, bg=BG_COLOR, highlightthickness=0, cursor="hand2")
        self.mic_btn_canvas.pack(side="left", expand=True)
        self._draw_mic_button(active=False)
        self.mic_btn_canvas.bind("<Button-1>", lambda e: self.on_mic_click())

        help_btn = tk.Label(mid_frame, text="❓", font=("Segoe UI Symbol", 9), bg=BG_COLOR, fg="#8E8E93", cursor="hand2")
        help_btn.pack(side="right", padx=10)
        help_btn.bind("<Button-1>", lambda e: self._show_help())
        help_btn.bind("<Enter>", lambda e: help_btn.config(fg="#FFFFFF"))
        help_btn.bind("<Leave>", lambda e: help_btn.config(fg="#8E8E93"))

        self.status_label = tk.Label(
            self.root, 
            text=self.hotkey_manager.get_display_text(), 
            font=("Microsoft JhengHei UI", 8), 
            bg=BG_COLOR, 
            fg="#8E8E93"
        )
        self.status_label.place(x=8, y=82, width=self.width-16, height=18)

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
        bg_circle_color = "#2E2E32" if not active else "#1C3552"
        icon_color = "#55B2FF" if not active else "#FF3B30"
        
        self.mic_btn_canvas.create_oval(2, 2, 44, 44, fill=bg_circle_color, outline="")
        mic_symbol = "🎙️" if not active else "⏹️"
        self.mic_btn_canvas.create_text(23, 23, text=mic_symbol, font=("Segoe UI Emoji", 13), fill=icon_color)

    def _open_settings_dialog(self):
        """彈出快捷鍵錄製與重設視窗（螢幕正中央）"""
        dialog = tk.Toplevel(self.root)
        dialog.title("設定快捷鍵")
        
        dialog_width = 280
        dialog_height = 180
        dialog.configure(bg="#222224")
        dialog.resizable(False, False)
        dialog.attributes("-topmost", True)

        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        center_x = int((screen_width - dialog_width) / 2)
        center_y = int((screen_height - dialog_height) / 2)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{center_x}+{center_y}")

        tk.Label(dialog, text="目前的快捷鍵：", font=("Microsoft JhengHei UI", 9), bg="#222224", fg="#8E8E93").pack(pady=(12, 2))

        record_btn = tk.Button(
            dialog, 
            text=self.hotkey_manager.get_display_text(), 
            font=("Segoe UI", 10, "bold"), 
            bg="#2E2E32", 
            fg="#55B2FF", 
            activebackground="#3A3A3E",
            activeforeground="#55B2FF",
            bd=1, 
            relief="solid",
            width=22,
            cursor="hand2"
        )
        record_btn.pack(pady=4, ipady=4)

        tip_label = tk.Label(dialog, text="點擊上方按鈕，按下新快捷鍵組合", font=("Microsoft JhengHei UI", 8), bg="#222224", fg="#8E8E93")
        tip_label.pack(pady=(2, 6))

        recording_state = {"is_recording": False, "recorded_keys": [], "pynput_listener": None}

        # 暫停目前的全局熱鍵監聽
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
                record_btn.config(text=display_txt, fg="#55B2FF", bg="#2E2E32")
                tip_label.config(text="✓ 已重設為預設 (CTRL+ALT+V)", fg="#34C759")
                self.status_label.config(text=display_txt)

        def start_recording():
            if recording_state["is_recording"]:
                return

            recording_state["is_recording"] = True
            recording_state["recorded_keys"].clear()
            record_btn.config(text="請按下組合鍵...", fg="#FF9500", bg="#3A3A2E")
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
                        # 1. 主鍵盤數字 0-9 (48-57)
                        if 48 <= vk <= 57:
                            return chr(vk)
                        # 2. 九宮格數字 0-9 (96-105)
                        if 96 <= vk <= 105:
                            return str(vk - 96)
                        # 3. 英文字母 A-Z (65-90)
                        if 65 <= vk <= 90:
                            return chr(vk).lower()

                        # 4. 常見標點符號 VK Code 手動映射
                        symbol_vk_map = {
                            186: ';', 187: '=', 188: ',', 189: '-', 190: '.', 191: '/',
                            192: '`', 219: '[', 220: '\\', 221: ']', 222: "'"
                        }
                        if vk in symbol_vk_map:
                            return symbol_vk_map[vk]

                        # 5. 利用 WinAPI 動態轉碼
                        try:
                            char_code = ctypes.windll.user32.MapVirtualKeyW(vk, 2)
                            if char_code > 0:
                                return chr(char_code).lower()
                        except Exception:
                            pass

                    # 6. 無 VK 碼時的備用處理
                    if hasattr(key, 'char') and key.char:
                        if ord(key.char) < 32:
                            return chr(ord(key.char) + 96)
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
                    # 定義標準修飾鍵順序 (CTRL -> ALT -> SHIFT -> CMD)
                    mod_order = {"<ctrl>": 1, "<alt>": 2, "<shift>": 3, "<cmd>": 4}

                    modifiers = [k for k in keys if k in mod_order]
                    normal_keys = [k for k in keys if k not in mod_order]

                    # 按標準權重排序
                    modifiers.sort(key=lambda x: mod_order.get(x, 99))
                    normal_keys.sort()

                    final_keys = modifiers + normal_keys
                    new_hotkey_str = "+".join(final_keys)

                    recording_state["is_recording"] = False
                    if recording_state["pynput_listener"]:
                        recording_state["pynput_listener"].stop()

                    if self.hotkey_manager.update_hotkey(new_hotkey_str):
                        display_txt = self.hotkey_manager.get_display_text()
                        record_btn.config(text=display_txt, fg="#34C759", bg="#2E2E32")
                        tip_label.config(text="✓ 設定成功！", fg="#34C759")
                        self.status_label.config(text=display_txt)
                    else:
                        record_btn.config(text="錯誤", fg="#FF3B30", bg="#2E2E32")
                        tip_label.config(text="不支援的組合，請重試", fg="#FF3B30")
                        self.hotkey_manager._start_listener()

                return False

            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            recording_state["pynput_listener"] = listener
            listener.start()

        record_btn.config(command=start_recording)

        reset_btn = tk.Button(
            dialog, 
            text="重設為預設值", 
            font=("Microsoft JhengHei UI", 8), 
            bg="#222224", 
            fg="#8E8E93", 
            activebackground="#222224",
            activeforeground="#FF3B30",
            bd=0, 
            cursor="hand2",
            command=reset_hotkey
        )
        reset_btn.pack(pady=(0, 4))

    def _show_help(self):
        messagebox.showinfo("使用說明", f"1. 按下快捷鍵 ({self.hotkey_manager.get_display_text()}) 開始錄音\n2. 對著麥克風講廣東話\n3. 識別後自動輸入至游標位置\n4. 點擊 ✕ 隱藏浮窗，可由右下角托盤重新呼出")

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
                state, msg, color = self.ui_queue.get_nowait()
                
                if msg:
                    self.status_label.config(text=msg, fg=color if color else "#8E8E93")
                
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
        
        chrome_options = Options()
        chrome_options.add_argument("--app=https://www.google.com")
        # 將初始位置移到極遠螢幕外，且尺寸設至最小 1x1，防止畫面對齊建立圖標
        chrome_options.add_argument("--window-position=-32000,-32000")
        chrome_options.add_argument("--window-size=1,1")
        chrome_options.add_argument("--use-fake-ui-for-media-stream")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        user_data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'Google', 'Chrome', 'User Data VoiceAppFix')
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

        self.driver = webdriver.Chrome(options=chrome_options)
        # 啟動瞬間即調用隱藏，移除延遲
        self._hide_chrome_window()

        self.driver.execute_cdp_cmd("Browser.grantPermissions", {
            "origin": "https://www.google.com",
            "permissions": ["audioCapture"]
        })

        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        
        self.wait = WebDriverWait(self.driver, 10)
        
        self.is_processing = False
        self.stop_event = threading.Event()
        self.reset_timer = None

    def _hide_chrome_window(self):
        try:
            # 立即獲取 Chrome 句柄並強制執行 SW_HIDE (0)，徹底消去工作列圖標
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

    def _reset_status_message(self):
        self.ui_queue.put(("IDLE", self.hotkey_manager.get_display_text(), "#8E8E93"))

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
            self.ui_queue.put(("LISTENING", "聆聽中...", "#55B2FF"))

            self.driver.get("https://www.google.com")

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
                self.ui_queue.put(("IDLE", f"✨ {recognized_text}", "#34C759"))
                self.kb_controller.type(recognized_text)
            else:
                self.ui_queue.put(("IDLE", "⚠️ 未聽清", "#FF9500"))

        except Exception as e:
            print(f"[系統提示]: {e}")
            self.ui_queue.put(("IDLE", self.hotkey_manager.get_display_text(), "#8E8E93"))
        finally:
            self.is_processing = False
            self.stop_event.clear()

            self.reset_timer = threading.Timer(3.0, self._reset_status_message)
            self.reset_timer.start()

    def trigger_speech(self):
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
    ui_queue = queue.Queue()
    
    hotkey_manager = DynamicHotkeyManager(action_callback=lambda: app.trigger_speech())
    
    app = VoiceInputApp(ui_queue, hotkey_manager)
    
    input_bar = CardVoiceUI(
        ui_queue, 
        on_mic_click_callback=app.trigger_speech,
        hotkey_manager=hotkey_manager,
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