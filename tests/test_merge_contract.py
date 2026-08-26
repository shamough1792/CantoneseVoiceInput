"""原始碼契約測試：驗證合併後 main.pyw 的剪貼簿開關契約存在。"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_FILE = os.path.join(PROJECT_ROOT, "main.pyw")

def _read_main():
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        return f.read()

SOURCE = _read_main()

def test_has_clipboard_queue_handler():
    assert 'item[0] == "CLIPBOARD"' in SOURCE
    assert "clipboard_clear()" in SOURCE
    assert "clipboard_append(text_to_copy)" in SOURCE

def test_clipboard_put_before_keyboard_input():
    clipboard_index = SOURCE.index('self.ui_queue.put(("CLIPBOARD", recognized_text))')
    keyboard_index = SOURCE.index("self.kb_controller.type(recognized_text)")
    assert clipboard_index < keyboard_index

def test_has_copy_to_clipboard_setting():
    assert 'self.copy_to_clipboard = load_config().get("copy_to_clipboard", False)' in SOURCE
    assert "def set_copy_to_clipboard(self, value):" in SOURCE
    assert "save_config({" in SOURCE

def test_has_config_functions():
    assert "def load_config():" in SOURCE
    assert "def save_config(config):" in SOURCE
    assert '"copy_to_clipboard": False' in SOURCE

def test_settings_dialog_has_checkbutton():
    assert "辨識後自動複製到剪貼簿" in SOURCE
    assert "tk.Checkbutton(" in SOURCE
