# 深淺模式即時切換實作計畫

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推薦）或 executing-plans 逐任務實作此計畫。步驟使用複選框（`- [ ]`）語法來追蹤進度。

**目標：** 在設定中加入可持續保存、即時套用到浮動工具列及設定／說明視窗的深色與淺色模式。

**架構：** `main.pyw` 提供語意色盤、設定驗證與合併保存，以及 UI 元件的主題註冊與重繪。模式變更在 Tkinter 主執行緒套用至目前存在的視窗；未開啟視窗建立時讀取目前模式。

**技術棧：** Python 3、Tkinter、pytest、PyInstaller。

---

## 檔案清單

- 修改：`main.pyw`，主題色盤、設定管理、視窗元件主題註冊、即時更新與外觀選擇控制。
- 建立：`tests/test_theme_contract.py`，沿用現有原始碼契約測試，驗證主題設定與 UI 接線。
- 建立：`docs/superpowers/plans/2026-10-20-theme-toggle.md`，本實作計畫。

## 任務 1：先建立回歸契約測試

**檔案：** 建立 `tests/test_theme_contract.py`。

- [ ] **步驟 1：新增契約測試**

```python
"""驗證深淺模式設定及 UI 接線契約。"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_FILE = os.path.join(PROJECT_ROOT, "main.pyw")
with open(MAIN_FILE, "r", encoding="utf-8") as f:
    SOURCE = f.read()


def test_dark_theme_is_the_legacy_default():
    assert '"theme": "dark"' in SOURCE


def test_dark_and_light_palettes_and_validation_exist():
    assert '"dark": {' in SOURCE
    assert '"light": {' in SOURCE
    assert 'theme not in THEME_PALETTES' in SOURCE
    assert 'isinstance(value, str)' in SOURCE


def test_config_updates_preserve_other_preferences():
    assert "current_config.update(config)" in SOURCE
    assert 'save_config({"theme": theme})' in SOURCE
    assert 'save_config({"copy_to_clipboard": self.copy_to_clipboard})' in SOURCE


def test_theme_updates_main_and_open_dialogs():
    assert "def apply_theme(self, theme):" in SOURCE
    assert "self.settings_dialog" in SOURCE
    assert "self.help_dialog" in SOURCE
    assert "self._draw_mic_button" in SOURCE


def test_settings_has_two_theme_choices():
    assert 'text="深色"' in SOURCE
    assert 'text="淺色"' in SOURCE
    assert "self.app.set_theme" in SOURCE
```

- [ ] **步驟 2：執行測試確認目前行為不符合新契約**

執行：`python -m pytest tests/test_theme_contract.py -q`。預期：測試因主題色盤、設定欄位、即時套用與控制項尚未實作而失敗。

## 任務 2：主題色盤與設定持久化

**檔案：** 修改 `main.pyw` 的設定常數、`load_config`、`save_config` 和 `VoiceInputApp`。

- [ ] **步驟 1：定義色盤和主題驗證**

建立 `THEME_PALETTES`，鍵為 `dark`、`light`，每個色盤包括 `bg`、`surface`、`surface_alt`、`border`、`text`、`muted`、`accent`、`mic_bg`、`mic_active`、`success`、`warning`、`error`、`hover`。設定預設及驗證：

```python
DEFAULT_CONFIG = {"copy_to_clipboard": False, "theme": "dark"}


def normalize_theme(value):
    return value if isinstance(value, str) and value in THEME_PALETTES else "dark"
```

`load_config()` 讀檔後合併預設，再正規化主題；讀檔失敗仍回傳兩個預設欄位。

- [ ] **步驟 2：保存設定時合併局部更新**

`save_config(config)` 先讀取目前設定，再用新值更新，確保更新其中一項不會清除另一項：

```python
current_config = load_config()
current_config.update(config)
current_config["theme"] = normalize_theme(current_config.get("theme"))
json.dump(current_config, f, ensure_ascii=False, indent=2)
```

- [ ] **步驟 3：為應用程式新增主題狀態與 setter**

`VoiceInputApp.__init__` 將 `load_config()` 結果讀取一次，設定 `self.theme`、`self.copy_to_clipboard` 和 `self.ui = None`。新增 setter：

```python
def set_theme(self, theme):
    if theme not in THEME_PALETTES:
        return False
    self.theme = theme
    save_config({"theme": theme})
    if self.ui and self.ui.root:
        self.ui.root.after(0, lambda: self.ui.apply_theme(theme))
    return True
```

保留 `set_copy_to_clipboard()` 現有接口，使用合併式保存。

- [ ] **步驟 4：執行設定契約測試**

執行：`python -m pytest tests/test_theme_contract.py -q`。預期：預設值、有效模式與設定保留相關測試通過。

## 任務 3：所有視窗的即時主題套用

**檔案：** 修改 `main.pyw` 的 `RoundedButton` 和 `CardVoiceUI`。

- [ ] **步驟 1：註冊元件色彩角色**

`CardVoiceUI.__init__` 設置 `self.theme = app.theme`、`self._theme_bindings = {}` 和麥克風 active 狀態，並設定 `app.ui = self`。使用角色註冊，不以目前顏色反推角色：

```python
def _register_theme_widget(self, window, widget, bg_role=None, fg_role=None):
    bindings = self._theme_bindings.setdefault(window, [])
    bindings.append((widget, bg_role, fg_role))
```

設定及說明視窗建立時註冊背景／文字角色，銷毀時移除綁定；每次更新前確認元件仍存在。

- [ ] **步驟 2：實作 `apply_theme(theme)`**

驗證主題並設定 `self.theme`；更新浮窗元件與已註冊的設定／說明元件；重繪圓角背景及麥克風 Canvas，保留錄音 active 狀態。所有 Tk 操作透過 `root.after(0, ...)` 在 UI 執行緒執行。

- [ ] **步驟 3：使佇列狀態顏色可隨主題變更**

狀態佇列第三欄改用 `accent`、`muted`、`success`、`warning`、`error` 角色；`_check_queue()` 依當前色盤解析文字顏色，避免切換後舊顏色再次寫回。麥克風繪圖函式也從目前色盤取色。

- [ ] **步驟 4：讓 `RoundedButton` 的繪製與 hover 依目前色盤刷新**

`configure(bg=..., fg=...)` 更新 Canvas 按鈕本身；Enter／Leave callback 在事件發生時讀取目前色盤，不保留舊模式顏色。切換後按鈕仍維持正確圓角、文字與 hover 效果。

- [ ] **步驟 5：更新設定和說明視窗建構器**

註冊標題列、背景、文字、提示、選項區、步驟列和按鈕色彩角色。設定視窗新增外觀區後調整高度，確保 footer 與重設按鈕不裁切。銷毀視窗時清除它的主題綁定。

- [ ] **步驟 6：執行主題契約測試**

執行：`python -m pytest tests/test_theme_contract.py -q`。預期：所有視窗更新和主題色角色契約通過。

## 任務 4：新增模式選擇及回歸驗證

**檔案：** 修改 `main.pyw` 設定對話框，必要時補充 `tests/test_theme_contract.py`。

- [ ] **步驟 1：新增深色／淺色分段控制**

在設定視窗加入「外觀」區塊和相鄰的「深色」「淺色」圓角選項。選取項使用 accent 樣式，未選項用次表面樣式。點選分別呼叫 `self.app.set_theme("dark")` 和 `self.app.set_theme("light")`；更新當前視窗選取樣式，不重建視窗、不清除快捷鍵錄製狀態。

- [ ] **步驟 2：檢查所有 hover 與狀態色**

快捷鍵錄製中、錄音中、成功、警告、錯誤與關閉按鈕皆讀取目前主題角色；維持狀態語意及文字對比。浮動工具列不增加標題。

- [ ] **步驟 3：執行完整自動驗證**

執行 `python -m pytest -q`、`python -m py_compile main.pyw`、`git diff --check`。預期：全部測試通過、語法檢查退出碼為 0、無 whitespace error。

- [ ] **步驟 4：手動驗證桌面流程**

啟動程式並確認：缺少 theme 的舊設定以深色啟動；兩種模式可反覆即時切換且同步影響浮窗及目前開啟的對話框；重啟後主題與剪貼簿偏好都保存；錄音中切換保留 active 狀態；熱鍵錄製、重設、hover、拖曳、關窗及視窗單例正常；所有內容不被裁切。

## 計畫自檢

- 規格的即時切換、三視窗同步、深淺色盤、舊設定 fallback、設定合併、語意狀態色、圓角 Canvas 重繪和防裁切均有任務覆蓋。
- 測試命令附預期結果，實際執行前不宣稱通過。
- 色盤唯一常數為 `THEME_PALETTES`；設定接口為 `VoiceInputApp.set_theme(theme)`，UI 接口為 `CardVoiceUI.apply_theme(theme)`。
