# 合併雙入口 + 剪貼簿開關 實現計劃

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推薦）或 superpowers:executing-plans 逐任務實現此計劃。步驟使用複選框（`- [ ]`）語法來跟蹤進度。

**目標：** 把 `main.pyw` 與 `main_2.pyw` 合併為單一 `main.pyw`，新增「辨識後自動複製到剪貼簿」設定開關（持久化到 `config.json`），刪除 `main_2.pyw`，更新 README。

**架構：** 沿用單一檔案 monolith 結構。`VoiceInputApp` 持有 `copy_to_clipboard` 狀態，`_process_speech` 依條件放 `CLIPBOARD` 進 queue；`CardVoiceUI` 的 `_check_queue` 處理剪貼簿寫入；設定視窗新增 Checkbutton；config 以 `%LOCALAPPDATA%\CantoneseVoiceInput\config.json` 持久化。Chrome 初始化沿用原 `main.pyw`（方案 B：`-32000,-32000`、`1x1`、`VoiceAppFix`），並保留 `_setup_permissions()` 與 `_ensure_driver_alive()`。

**技術棧：** Python 3.8+、Tkinter、json、Selenium、pynput、pystray。

---

## 檔案與責任

- 修改：`main.pyw`
  - 頂部新增 `import json`、`DEFAULT_CONFIG`、`CONFIG_DIR`、`load_config()`、`save_config()`。
  - `CardVoiceUI.__init__` 接收 `app` 參考，`_check_queue` 加入 CLIPBOARD 處理。
  - `VoiceInputApp.__init__` 讀取 `copy_to_clipboard`，新增 `set_copy_to_clipboard()`。
  - `_process_speech` 成功分支改為條件放剪貼簿。
  - `_open_settings_dialog` 新增剪貼簿 Checkbutton、加大視窗高度。
  - `_show_help` 說明文字依開關動態顯示。
  - `__main__` 把 `app` 傳入 `CardVoiceUI`。
- 刪除：`main_2.pyw`
- 修改：`README.md`
  - 移除雙入口說明，改為單入口 + 剪貼簿開關。
- 建立：`tests/test_merge_contract.py`
  - 原始碼契約測試（純文字檢查）。

---

### Task 1：新增 config 工具函式與剪貼簿契約測試

**檔案：**
- 修改：`main.pyw:1-33`（頂部 import 與常數區）
- 建立：`tests/test_merge_contract.py`

- [ ] **步驟 1：建立失敗測試**

建立 `tests/test_merge_contract.py`：

```python
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
```

- [ ] **步驟 2：執行測試確認失敗**

運行：`python -m pytest tests/test_merge_contract.py -q`
預期：FAIL（`main.pyw` 尚無這些字串）

- [ ] **步驟 3：在 `main.pyw` 新增 config 工具**

在檔案頂部 import 區新增 `import json`：

```python
import json
```

在 `WS_EX_NOACTIVATE = 0x08000000` 之後新增：

```python
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
```

- [ ] **步驟 4：執行測試確認部分通過**

運行：`python -m pytest tests/test_merge_contract.py -q`
預期：`test_has_config_functions` PASS，其餘仍 FAIL

- [ ] **步驟 5：Commit**

```bash
git add main.pyw
git commit -m "feat: add config persistence for clipboard toggle"
```

---

### Task 2：`VoiceInputApp` 加入剪貼簿開關

**檔案：**
- 修改：`main.pyw:539-544`（`VoiceInputApp.__init__`）
- 修改：`main.pyw:673-680`（`_process_speech` 成功分支）

- [ ] **步驟 1：確認測試仍失敗**

運行：`python -m pytest tests/test_merge_contract.py -q`
預期：`test_has_copy_to_clipboard_setting` 仍 FAIL

- [ ] **步驟 2：`VoiceInputApp.__init__` 讀取設定**

在 `__init__` 中 `self.driver = None` 之後新增：

```python
        self.copy_to_clipboard = load_config().get("copy_to_clipboard", False)
```

- [ ] **步驟 3：`_process_speech` 改為條件放剪貼簿**

把成功分支改為：

```python
            if recognized_text:
                play_sound("success")

                if self.copy_to_clipboard:
                    self.ui_queue.put(("CLIPBOARD", recognized_text))

                display_text = recognized_text if len(recognized_text) <= 12 else recognized_text[:12] + "..."

                self.ui_queue.put(("IDLE", f"✨ {display_text}", "#107c10"))

                self.kb_controller.type(recognized_text)
```

- [ ] **步驟 4：新增 `set_copy_to_clipboard` 方法**

在 `_reset_status_message` 之前新增：

```python
    def set_copy_to_clipboard(self, value):
        self.copy_to_clipboard = bool(value)
        save_config({"copy_to_clipboard": self.copy_to_clipboard})
```

- [ ] **步驟 5：執行測試**

運行：`python -m pytest tests/test_merge_contract.py -q`
預期：`test_has_copy_to_clipboard_setting` PASS、`test_clipboard_put_before_keyboard_input` PASS

- [ ] **步驟 6：Commit**

```bash
git add main.pyw
git commit -m "feat: add clipboard toggle state to voice app"
```

---

### Task 3：`CardVoiceUI` 處理剪貼簿 queue 與設定視窗

**檔案：**
- 修改：`main.pyw:111-115`（`CardVoiceUI.__init__`）
- 修改：`main.pyw:519-536`（`_check_queue`）
- 修改：`main.pyw:256-415`（`_open_settings_dialog`）
- 修改：`main.pyw:417-474`（`_show_help`）
- 修改：`main.pyw:760-765`（`__main__` 傳入 app）

- [ ] **步驟 1：`CardVoiceUI.__init__` 接收 `app` 參考**

改為：

```python
    def __init__(self, ui_queue, on_mic_click_callback, hotkey_manager, app, on_close_callback=None):
        self.ui_queue = ui_queue
        self.on_mic_click = on_mic_click_callback
        self.hotkey_manager = hotkey_manager
        self.app = app
        self.on_close_callback = on_close_callback
```

- [ ] **步驟 2：`_check_queue` 加入 CLIPBOARD 處理**

把迴圈內改為：

```python
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
```

- [ ] **步驟 3：設定視窗新增 Checkbutton 並加高**

把 `dialog_height = 184` 改為 `dialog_height = 214`。

在 `reset_btn.pack(pady=(0, 4))` 之前（`record_btn.config(command=start_recording)` 之後）插入：

```python
        clip_var = tk.BooleanVar(value=self.app.copy_to_clipboard)
        cb = tk.Checkbutton(
            dialog, text="辨識後自動複製到剪貼簿",
            variable=clip_var, bg=COLOR_BG, fg=COLOR_ICON,
            activebackground=COLOR_BG, activeforeground=COLOR_ICON,
            selectcolor=COLOR_MIC_BG, font=("Microsoft JhengHei UI", 9),
            command=lambda: self.app.set_copy_to_clipboard(clip_var.get())
        )
        cb.pack(pady=(2, 2))
```

- [ ] **步驟 4：`_show_help` 說明文字依開關動態顯示**

把 `help_text` 改為：

```python
        copy_note = "並複製至剪貼簿" if self.app.copy_to_clipboard else ""
        help_text = (
            f"1. 按下快捷鍵 ({current_hotkey}) 開始錄音\n"
            "2. 對著麥克風講廣東話\n"
            f"3. 識別後將自動輸入至游標位置{copy_note}\n"
            "4. 點擊 ✕ 可隱藏浮窗，由右下角托盤重啟"
        )
```

- [ ] **步驟 5：`__main__` 傳入 app**

改為：

```python
        input_bar = CardVoiceUI(
            ui_queue,
            on_mic_click_callback=app.trigger_speech,
            hotkey_manager=hotkey_manager,
            app=app,
            on_close_callback=app.quit
        )
```

- [ ] **步驟 6：執行測試與語法檢查**

運行：`python -m pytest tests/test_merge_contract.py -q`
預期：全部 PASS（含 `test_has_clipboard_queue_handler`、`test_settings_dialog_has_checkbutton`）

運行：`python -m py_compile main.pyw`
預期：無輸出，回傳碼 0

- [ ] **步驟 7：Commit**

```bash
git add main.pyw
git commit -m "feat: add clipboard toggle UI and queue handling"
```

---

### Task 4：刪除 `main_2.pyw` 並更新 README

**檔案：**
- 刪除：`main_2.pyw`
- 修改：`README.md:9-11`

- [ ] **步驟 1：刪除 `main_2.pyw`**

```bash
git rm main_2.pyw
```

- [ ] **步驟 2：更新 README 雙入口說明**

把：

```markdown
專案提供兩個獨立入口：
- `main.pyw`：辨識成功後自動輸入到目前游標位置。
- `main_2.pyw`：辨識成功後同時寫入系統剪貼簿，並自動輸入到目前游標位置。
```

改為：

```markdown
專案提供單一入口 `main.pyw`：辨識成功後自動輸入到目前游標位置。
在設定視窗中可勾選「辨識後自動複製到剪貼簿」，勾選後辨識成功會同時複製到系統剪貼簿。
```

- [ ] **步驟 3：執行最終驗證**

```bash
python -m py_compile main.pyw
python -m pytest tests/test_merge_contract.py -q
git diff --check
git status --short
```

預期：`py_compile` 無輸出；測試全部 PASS；`git diff --check` 無輸出；`git status` 顯示 `main_2.pyw` 被刪除、`main.pyw` 與 `README.md` 已修改。

- [ ] **步驟 4：Commit**

```bash
git add main.pyw README.md
git commit -m "feat: merge dual entrypoints into single main with clipboard toggle"
```

---

### Task 5：最終回歸驗證

**檔案：**
- 驗證：`main.pyw`

- [ ] **步驟 1：完整測試套件**

運行：`python -m pytest tests/test_merge_contract.py -v`
預期：5 個測試全部 PASS

- [ ] **步驟 2：語法與差異檢查**

運行：`python -m py_compile main.pyw && git diff --check`
預期：皆無輸出

- [ ] **步驟 3：手動啟動驗證**

運行：`python main.pyw`
檢查點：
- 浮窗正常顯示、可拖曳
- 設定視窗含「辨識後自動複製到剪貼簿」勾選框
- 勾選後重啟程式，狀態仍記憶（`%LOCALAPPDATA%\CantoneseVoiceInput\config.json` 存在且含 `true`）
- 勾選時辨識成功後文字進入系統剪貼簿並自動輸入
- 未勾選時只自動輸入，不寫剪貼簿

- [ ] **步驟 4：確認刪除 `main_2.pyw` 後無殘留引用**

運行：`grep -rn "main_2" README.md main.pyw || echo "無殘留"`

- [ ] **步驟 5：Commit（若 README 或驗證有補充）**

```bash
git add -A
git commit -m "chore: final regression check for merged entry"
```
