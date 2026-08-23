import time
import re
import os
import ctypes
import threading
import queue
import tkinter as tk
import pyperclip
import pyautogui
from pynput import keyboard
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
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SW_HIDE = 0

def is_garbage_token(text):
    return bool(len(text) > 30 and re.match(r'^[A-Za-z0-9_\-]+$', text))

def hide_window_from_taskbar(driver):
    """使用 Windows API 強制隱藏 Chrome 視窗與工作列圖標"""
    try:
        time.sleep(0.5)
        hwnd = ctypes.windll.user32.FindWindowW(None, driver.title)
        if not hwnd:
            hwnd = ctypes.windll.user32.FindWindowW("Chrome_WidgetWin_1", None)

        if hwnd:
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
            ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
    except Exception as e:
        print(f"[警告] 隱藏工作列圖標失敗: {e}")

def create_tray_icon_image():
    """動態生成托盤麥克風圖示 (32x32)"""
    width, height = 32, 32
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    # 繪製圓形底色與簡易圖標
    dc.ellipse((2, 2, 30, 30), fill='#1E1E1E', outline='#40A9FF', width=2)
    dc.rectangle((13, 8, 19, 18), fill='#40A9FF')
    dc.arc((10, 12, 22, 22), 0, 180, fill='#40A9FF', width=2)
    dc.line((16, 22, 16, 26), fill='#40A9FF', width=2)
    dc.line((12, 26, 20, 26), fill='#40A9FF', width=2)
    return image

class PersistentVoiceBarUI:
    def __init__(self, ui_queue, on_mic_click_callback, on_close_callback=None):
        self.ui_queue = ui_queue
        self.on_mic_click = on_mic_click_callback
        self.on_close_callback = on_close_callback
        self.root = None
        self.mic_button = None
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
        
        TRANS_COLOR = "#010101"
        BG_COLOR = "#1E1E1E"
        BORDER_COLOR = "#333333"

        self.root.config(bg=TRANS_COLOR)
        self.root.wm_attributes("-transparentcolor", TRANS_COLOR)
        self.root.attributes("-alpha", 0.95)

        self.root.protocol("WM_DELETE_WINDOW", self.hide_ui)

        self.width = 380
        self.height = 44
        self.radius = 22

        self.canvas = tk.Canvas(
            self.root, 
            width=self.width, 
            height=self.height, 
            bg=TRANS_COLOR, 
            highlightthickness=0
        )
        self.canvas.pack()

        self._draw_capsule(BG_COLOR, outline_color=BORDER_COLOR)

        content_frame = tk.Frame(self.canvas, bg=BG_COLOR)
        self.canvas.create_window(self.width // 2, self.height // 2, window=content_frame, anchor="center")

        self.mic_button = tk.Button(
            content_frame,
            text="🎙️",
            font=("Segoe UI Emoji", 11),
            bg=BG_COLOR,
            fg="#40A9FF",
            activebackground="#2A2A2A",
            activeforeground="#73D13D",
            bd=0,
            padx=6,
            pady=2,
            cursor="hand2",
            command=self.on_mic_click,
            takefocus=False
        )
        self.mic_button.pack(side="left", padx=(6, 4))

        self.status_label = tk.Label(
            content_frame,
            text="廣東話語音輸入法 (Ctrl+Alt+V)",
            font=("Microsoft JhengHei UI", 10, "bold"),
            bg=BG_COLOR,
            fg="#E6E6E6"
        )
        self.status_label.pack(side="left", padx=(4, 6))

        close_button = tk.Button(
            content_frame,
            text="✕",
            font=("Microsoft JhengHei UI", 9),
            bg=BG_COLOR,
            fg="#8C8C8C",
            activebackground="#FF4D4F",
            activeforeground="#FFFFFF",
            bd=0,
            padx=6,
            pady=2,
            cursor="hand2",
            command=self.hide_ui,  # 按下 ✕ 時預設隱藏至系統托盤
            takefocus=False
        )
        close_button.pack(side="right", padx=(2, 6))

        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._do_drag)
        self.status_label.bind("<ButtonPress-1>", self._start_drag)
        self.status_label.bind("<B1-Motion>", self._do_drag)

        self.root.update_idletasks()

        # 關鍵位置計算：定位於螢幕右下角 (保留 60px 避開工作列)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_pos = screen_width - self.width - 20
        y_pos = screen_height - self.height - 60
        self.root.geometry(f"{self.width}x{self.height}+{x_pos}+{y_pos}")

        self._prevent_focus()

        self.root.after(50, self._check_queue)
        self.root.mainloop()

    def toggle_ui(self):
        """切換懸浮框顯示/隱藏"""
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
        """徹底退出程式"""
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

    def _draw_capsule(self, fill_color, outline_color):
        r = self.radius
        w = self.width
        h = self.height
        
        self.canvas.create_arc(0, 0, r*2, h, start=90, extent=180, fill=fill_color, outline=outline_color, width=1)
        self.canvas.create_arc(w-r*2, 0, w, h, start=270, extent=180, fill=fill_color, outline=outline_color, width=1)
        self.canvas.create_rectangle(r, 0, w-r, h, fill=fill_color, outline=fill_color)
        
        self.canvas.create_line(r, 0, w-r, 0, fill=outline_color)
        self.canvas.create_line(r, h-1, w-r, h-1, fill=outline_color)

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
                    self.status_label.config(text=msg, fg=color if color else "#E6E6E6")
                
                if state == "LISTENING":
                    self.mic_button.config(text="⏹️", fg="#FF4D4F", bg="#2A2A2A")
                elif state == "IDLE":
                    self.mic_button.config(text="🎙️", fg="#40A9FF", bg="#1E1E1E")
                    
        except Exception:
            pass
            
        if self.root:
            self.root.after(50, self._check_queue)

class VoiceInputApp:
    def __init__(self, ui_queue):
        self.ui_queue = ui_queue
        
        chrome_options = Options()
        chrome_options.add_argument("--use-fake-ui-for-media-stream")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        
        chrome_options.add_argument("--app=https://www.google.com")
        chrome_options.add_argument("--window-position=-32000,-32000")
        chrome_options.add_argument("--window-size=800,600")
        
        user_data_dir = os.path.join(os.environ['LOCALAPPDATA'], 'Google', 'Chrome', 'User Data VoiceAppFix')
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
        except Exception:
            os.system("taskkill /f /im chromedriver.exe >nul 2>&1")
            self.driver = webdriver.Chrome(options=chrome_options)

        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        
        self.wait = WebDriverWait(self.driver, 10)
        
        self.is_processing = False
        self.stop_event = threading.Event()
        self.reset_timer = None

        hide_window_from_taskbar(self.driver)

    def quit(self):
        if self.reset_timer:
            self.reset_timer.cancel()
        try:
            if self.driver:
                self.driver.quit()
        except Exception as e:
            print(f"[警告] 關閉 Chrome 時發生例外: {e}")

    def _reset_status_message(self):
        self.ui_queue.put(("IDLE", "廣東話語音輸入法 (Ctrl+Alt+V)", "#E6E6E6"))

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
            self.ui_queue.put(("LISTENING", "聆聽中，請說話...", "#40A9FF"))

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
                self.ui_queue.put(("IDLE", f"✨ {recognized_text}", "#73D13D"))
                pyperclip.copy(recognized_text)
                time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'v')
            else:
                self.ui_queue.put(("IDLE", "⚠️ 未聽清，請再試一次", "#FFA940"))

        except Exception as e:
            print(f"[系統提示]: {e}")
            self.ui_queue.put(("IDLE", "廣東話語音輸入法 (Ctrl+Alt+V)", "#E6E6E6"))
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
    """建立並啟動 System Tray 圖示與選單"""
    def on_toggle_click(icon, item):
        input_bar.root.after(0, input_bar.toggle_ui)

    def on_exit_click(icon, item):
        icon.stop()
        input_bar.root.after(0, input_bar.destroy_app)

    menu = pystray.Menu(
        pystray.MenuItem("顯示/隱藏膠囊", on_toggle_click, default=True),
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
    app = VoiceInputApp(ui_queue)
    
    def start_hotkey():
        with keyboard.GlobalHotKeys({'<ctrl>+<alt>+v': app.trigger_speech}) as hk:
            hk.join()

    threading.Thread(target=start_hotkey, daemon=True).start()
    
    input_bar = PersistentVoiceBarUI(
        ui_queue, 
        on_mic_click_callback=app.trigger_speech,
        on_close_callback=app.quit
    )

    # 在獨立背景執行緒啟動系統托盤
    tray_icon_holder = {}
    tray_thread = threading.Thread(
        target=setup_tray_icon, 
        args=(input_bar, tray_icon_holder), 
        daemon=True
    )
    tray_thread.start()

    input_bar.start()