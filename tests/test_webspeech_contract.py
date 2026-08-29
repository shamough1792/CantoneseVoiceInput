"""原始碼契約測試：驗證 main.pyw 改用 webkitSpeechRecognition 直接識別。"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_FILE = os.path.join(PROJECT_ROOT, "main.pyw")

def _read_main():
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        return f.read()

SOURCE = _read_main()

def test_uses_webspeech_recognition():
    assert "webkitSpeechRecognition" in SOURCE

def test_uses_onresult_event():
    assert "onresult" in SOURCE

def test_uses_voice_result_bridge():
    assert "window.__voiceResult" in SOURCE

def test_no_google_button_click_anymore():
    assert "element_to_be_clickable" not in SOURCE

def test_no_name_q_polling_anymore():
    assert 'By.NAME, "q"' not in SOURCE
    assert "_get_current_text" not in SOURCE
    assert "is_garbage_token" not in SOURCE

def test_error_mapping_present():
    assert '"no-speech"' in SOURCE
    assert '"not-allowed"' in SOURCE


def test_manual_stop_plays_fail_sound():
    stop_branch = SOURCE[SOURCE.index("if self.is_processing:"):]
    stop_branch = stop_branch[:stop_branch.index("self.is_processing = True")]
    assert 'self.stop_event.set()' in stop_branch
    assert 'play_sound("fail")' in stop_branch
