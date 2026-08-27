# 合併雙入口 + 剪貼簿開關 設計規格

**日期：** 2026-08-26

## 目標

把 `main.pyw` 與 `main_2.pyw` 兩個幾乎重複的入口合併為單一 `main.pyw`，並在設定視窗中新增「辨識後自動複製到剪貼簿」的可勾選開關，使用者可自行決定是否在語音辨識成功後同步複製到系統剪貼簿。開關狀態需持久化，重啟程式後仍記住上次選擇。

## 背景

- 兩個檔案約 95% 程式碼相同，差異集中在：
  1. 剪貼簿處理（`main_2.pyw` 有 `CLIPBOARD` queue 流程）
  2. Chrome 初始化細節（視窗位置、User Data 資料夾、`--remote-allow-origins`）
  3. `main.pyw` 有 `_ensure_driver_alive()`（崩潰重啟）與 `_setup_permissions()`（麥克風權限），`main_2.pyw` 沒有
  4. 幫助文字差異
  5. 少數殘留舊色值（已修復）
- 每次修改都要同步兩邊，維護成本高。

## 範圍

### 包含
- 合併兩個入口為單一 `main.pyw`
- 新增 `copy_to_clipboard` 可勾選設定，於設定視窗中操作
- 設定持久化到 `config.json`
- Chrome 初始化採用原 `main.pyw` 的設定（方案 B）
- 保留 `_ensure_driver_alive()` 與 `_setup_permissions()`
- 刪除 `main_2.pyw`
- 更新 README 說明

### 不包含
- 不抽共用模組（維持 single-file monolith 的現有風格）
- 不改變語音辨識流程、熱鍵設定、托盤行為
- 不新增其他設定項目
- 不新增外部依賴

## 技術決策

### Chrome 初始化（採用方案 B）

沿用原 `main.pyw` 的參數：
- `--window-position=-32000,-32000`
- `--window-size=1,1`
- User Data 資料夾：`%LOCALAPPDATA%\Google\Chrome\User Data VoiceAppFix`
- 保留 `_setup_permissions()`（麥克風權限 CDP 設定）
- 保留 `_ensure_driver_alive()`（Chrome 崩潰自動重啟）

### 設定持久化

新增 `config.json`，位於 `%LOCALAPPDATA%\CantoneseVoiceInput\config.json`：

```json
{
  "copy_to_clipboard": false
}
```

- 預設 `false`（不改變原本只打字的用戶習慣）
- 載入時與預設值合併，缺欄位補回
- 儲存時以 UTF-8 寫入

## 元件變更

### 新增工具函式（檔案頂部）

```python
import json

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

### `VoiceInputApp`

- `__init__` 讀取設定：
  ```python
  self.copy_to_clipboard = load_config().get("copy_to_clipboard", False)
  ```
- `_process_speech` 辨識成功分支改為條件放剪貼簿：
  ```python
  if recognized_text:
      play_sound("success")
      if self.copy_to_clipboard:
          self.ui_queue.put(("CLIPBOARD", recognized_text))
      display_text = recognized_text if len(recognized_text) <= 12 else recognized_text[:12] + "..."
      self.ui_queue.put(("IDLE", f"✨ {display_text}", "#107c10"))
      self.kb_controller.type(recognized_text)
  ```
- 新增方法：
  ```python
  def set_copy_to_clipboard(self, value):
      self.copy_to_clipboard = bool(value)
      save_config({"copy_to_clipboard": self.copy_to_clipboard})
  ```

### `CardVoiceUI`

- `__init__` 需取得 `VoiceInputApp` 參考（或傳入 `copy_to_clipboard` 值與 setter），用於設定視窗讀寫開關。採傳入 app 實體，貼近現有程式風格。
- `_check_queue` 加入 `CLIPBOARD` 處理塊：
  ```python
  if isinstance(item, tuple) and item[0] == "CLIPBOARD":
      text_to_copy = item[1]
      try:
          self.root.clipboard_clear()
          self.root.clipboard_append(text_to_copy)
          self.root.update()
      except Exception as clip_err:
          print(f"[剪貼簿錯誤]: {clip_err}")
      continue
  ```
- `_open_settings_dialog` 在「重設為預設值」按鈕上方新增 Checkbutton：
  ```python
  clip_var = tk.BooleanVar(value=app.copy_to_clipboard)
  cb = tk.Checkbutton(
      dialog, text="辨識後自動複製到剪貼簿",
      variable=clip_var, bg=COLOR_BG, fg=COLOR_ICON,
      activebackground=COLOR_BG, activeforeground=COLOR_ICON,
      selectcolor=COLOR_MIC_BG, font=("Microsoft JhengHei UI", 9),
      command=lambda: app.set_copy_to_clipboard(clip_var.get())
  )
  ```
- 設定視窗高度需加大以容納新元件（例如 184 → 約 214）
- `_show_help` 說明文字改為依開關狀態動態顯示是否複製到剪貼簿

## 資料流

```
勾選開關 → app.set_copy_to_clipboard(True) → 寫回 config.json
觸發語音 → _process_speech 辨識成功
          → copy_to_clipboard=True 時 put(("CLIPBOARD", text))
          → put(("IDLE", 顯示, 綠)) → kb_controller.type(text)
→ _check_queue 輪詢 → 更新狀態列 + 若為 CLIPBOARD 則複製到系統剪貼簿 + 自動打字
```

## 錯誤處理

- `load_config` / `save_config` 皆以 try/except 包住，config 損壞或不可寫時回退預設 `False`，不阻斷程式。
- 剪貼簿寫入沿用現有 try/except 列印 `[剪貼簿錯誤]`。
- config 寫入失敗只印警告，不中斷使用者操作。

## 測試

- 補一份「剪貼簿契約」的**原始碼契約測試**（純文字檢查 `main.pyw`）：
  - `_check_queue` 含 `item[0] == "CLIPBOARD"`、`clipboard_clear()`、`clipboard_append`
  - `_process_speech` 中 CLIPBOARD 的 put 在 `kb_controller.type` 之前
  - `set_copy_to_clipboard` 存在
  - 預設 `copy_to_clipboard = False`

## 驗證

- `python -m py_compile main.pyw` 通過
- `git diff --check` 通過
- 刪除 `main_2.pyw` 後 `git status` 正確
- 實際啟動 `main.pyw`：
  - 浮窗正常顯示
  - 設定視窗含剪貼簿勾選框
  - 勾選後重啟程式，狀態仍記憶
  - 勾選時辨識成功後文字進入系統剪貼簿並自動輸入
  - 未勾選時只自動輸入，不寫剪貼簿
