# 改用 webkitSpeechRecognition 直接識別 實現計劃

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推薦）或 superpowers:executing-plans 逐任務實現此計劃。步驟使用複選框（`- [ ]`）語法來跟蹤進度。

**目標：** 把 `main.pyw` 的語音觸發從「點擊 Google 語音按鈕 + 輪詢 `name=q`」改為「注入 `webkitSpeechRecognition` + `onresult` 事件取文字」，移除對 Google 前端 DOM 的依賴。

**架構：** 在 `VoiceInputApp` 新增 `SPEECH_JS` 常數與 `_capture_speech()`，`_process_speech` 呼叫它取得 `(transcript, error)` 後沿用既有成功/失敗流程；刪除 `_get_current_text`、`is_garbage_token` 及因此無用的 `re`/`By`/`EC` import。以「原始碼契約測試」驗證新寫法存在、舊寫法消失。

**技術棧：** Python 3.8+、Tkinter、Selenium、pytest（僅契約測試）。

---

## 檔案與責任

- 修改：`main.pyw`
  - `VoiceInputApp`：新增 `SPEECH_JS` 與 `_capture_speech()`（`_process_speech` 之前）
  - 重寫 `VoiceInputApp._process_speech`（約 688-746 行）
  - 刪除 `VoiceInputApp._get_current_text`（約 678-686 行）
  - 刪除 `is_garbage_token`（67-68 行）
  - 移除 `import re`（第 2 行）、`from selenium.webdriver.common.by import By`（第 15 行）、`from selenium.webdriver.support import expected_conditions as EC`（第 19 行）
- 建立：`tests/test_webspeech_contract.py`（原始碼契約測試）

> 附註：`self.wait = WebDriverWait(self.driver, 10)`（`_setup_permissions` 內）與 `WebDriverWait` import 保留（不影響行為）。

---

### Task 1：新增失敗契約測試

**檔案：**
- 建立：`tests/test_webspeech_contract.py`

- [ ] **步驟 1：建立測試檔**

建立 `tests/test_webspeech_contract.py`：

```python
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
```

- [ ] **步驟 2：執行測試確認失敗**

運行：`python -m pytest tests/test_webspeech_contract.py -q`
預期：`test_uses_webspeech_recognition` FAIL（`main.pyw` 尚無 `webkitSpeechRecognition`），其餘新測試亦 FAIL 或 PASS 依現況（`test_no_google_button_click_anymore` 因仍有 `element_to_be_clickable` 而 FAIL）。

- [ ] **步驟 3：Commit（僅測試檔，紅燈狀態）**

```bash
git add tests/test_webspeech_contract.py
git commit -m "test: add contract tests for direct webspeech recognition"
```

---

### Task 2：實作直接識別

**檔案：**
- 修改：`main.pyw`
  - 新增 `SPEECH_JS` 與 `_capture_speech()`（放在 `_process_speech` 之前）
  - 重寫 `_process_speech`
  - 刪除 `_get_current_text`、`is_garbage_token`
  - 移除 `import re`、`By`、`EC` import

- [ ] **步驟 1：新增 `SPEECH_JS` 常數與 `_capture_speech()`**

在 `_process_speech` 之前插入（原 `_get_current_text` 的位置）：

```python
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
```

- [ ] **步驟 2：重寫 `_process_speech`**

把現有整個 `_process_speech`（從 `play_sound("start")` 到 `else: self.ui_queue.put(("IDLE", "⚠️ 未聽清", "#c19c00"))`，含 `mic_button = self.wait.until(...)` 與輪詢 `name=q` 的段落）替換為：

```python
    def _process_speech(self):
        if self.reset_timer:
            self.reset_timer.cancel()

        try:
            play_sound("start")
            self.ui_queue.put(("LISTENING", "聆聽中...", COLOR_ACCENT))

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

                self.ui_queue.put(("IDLE", f"✨ {display_text}", "#107c10"))

                self.kb_controller.type(recognized_text)
            elif error == "no-speech":
                self.ui_queue.put(("IDLE", "⚠️ 未聽清", "#c19c00"))
            elif error in ("not-allowed", "service-not-allowed"):
                self.ui_queue.put(("IDLE", "❌ 麥克風權限被拒", "#d13438"))
            elif error == "network":
                self.ui_queue.put(("IDLE", "❌ 無法連線識別", "#d13438"))
            elif error == "aborted":
                self.ui_queue.put(("IDLE", self.hotkey_manager.get_display_text(), COLOR_ICON))
            else:
                self.ui_queue.put(("IDLE", "⚠️ 識別失敗", "#c19c00"))

        except Exception as e:
            print(f"[系統提示]: {e}")
            self.ui_queue.put(("IDLE", self.hotkey_manager.get_display_text(), COLOR_ICON))
        finally:
            self.is_processing = False
            self.stop_event.clear()

            self.reset_timer = threading.Timer(3.0, self._reset_status_message)
            self.reset_timer.start()
```

- [ ] **步驟 3：刪除舊碼**

刪除：
- `_get_current_text` 整個方法（原 678-686 行，含 `def _get_current_text(self):` 至 `return ""`）。
- `is_garbage_token` 整個函式（原 67-68 行，含 `def is_garbage_token(text):` 與其 `return`）。

- [ ] **步驟 4：移除無用 import**

刪除下列三行（確認改動後全檔不再使用它們）：
- 第 2 行 `import re`
- 第 15 行 `from selenium.webdriver.common.by import By`
- 第 19 行 `from selenium.webdriver.support import expected_conditions as EC`

- [ ] **步驟 5：執行全部測試確認通過**

運行：`python -m pytest tests/ -q`
預期：`test_webspeech_contract.py` 6 個測試 + `test_merge_contract.py` 5 個測試，**全部 PASS**。

- [ ] **步驟 6：語法與差異檢查**

運行：`python -m py_compile main.pyw && git diff --check`
預期：皆無輸出、回傳碼 0。

- [ ] **步驟 7：Commit**

```bash
git add main.pyw
git commit -m "feat: use webkitSpeechRecognition directly for speech capture"
```

---

### Task 3：最終回歸驗證

**檔案：**
- 驗證：`main.pyw`、`tests/`

- [ ] **步驟 1：完整測試套件**

運行：`python -m pytest tests/ -v`
預期：11 個測試全部 PASS。

- [ ] **步驟 2：確認無舊寫法殘留**

運行：`python -c "import pathlib; s=pathlib.Path('main.pyw').read_text(encoding='utf-8'); print('OK' if ('element_to_be_clickable' not in s and 'By.NAME' not in s and 'is_garbage_token' not in s) else 'FAIL')"`
預期：`OK`。

- [ ] **步驟 3：手動真機驗證（使用者執行）**

運行：`python main.pyw`
檢查點：
- 浮窗正常顯示、熱鍵 `Ctrl+Alt+V` 可觸發
- 講粵語後狀態列顯示成功（綠字）、文字自動輸入到游標
- 設定視窗「辨識後自動複製到剪貼簿」開關行為不變
- 無語音時約 10 秒內顯示「⚠️ 未聽清」

- [ ] **步驟 4：Commit（若驗證過程有補充）**

```bash
git add -A
git commit -m "chore: final regression check for webspeech recognition"
```
