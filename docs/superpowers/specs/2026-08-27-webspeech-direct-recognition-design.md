# 改用 webkitSpeechRecognition 直接識別 設計規格

**日期：** 2026-08-27
**分支：** `feat/webspeech-direct-recognition`
**範圍：** 把 `main.pyw` 的語音觸發從「點擊 Google 語音按鈕 + 輪詢 `name=q`」改為「直接呼叫 `webkitSpeechRecognition` + `onresult` 事件取文字」，以抵抗 Google 前端 DOM 改版。

## 目標

1. 移除對 Google 網頁 DOM 的依賴：
   - 不再用 `element_to_be_clickable(//*[@aria-label='語音搜尋' or @aria-label='Search by voice'])` 點擊語音按鈕（最容易改版的選擇器）。
   - 不再靠 `find_element(By.NAME, "q")` 輪詢識別文字（結果落點沒有契約保證）。
2. 改為事件驅動：注入頁面的 `webkitSpeechRecognition` 以 `onresult` 事件直接取得粵語文字。
3. 已由 Spike 實證：Chrome 151 下「`execute_script` 直接 `start()`」**無需使用者手勢**即可觸發 `onstart`；真機上 `onresult` 正確返回「今日天氣好唔好」。

## 背景

- 現行 `_process_speech`（`main.pyw:688-746`）依賴「語音按鈕 `aria-label`」與「結果寫入 `name=q`」兩處 Google DOM。
- `aria-label` 是 UX 文案非介面契約，有實際改版歷史（已見 `'Search by voice'` 等變體）；`name="q"` 雖極穩定，但「語音結果落點」並無保證。
- 目標是保留「免費蹭 Google 網頁語音」的本質（仍需載入 `google.com.hk` + 麥克風授權 + 網路），只移除可免的脆弱環節。

## 範圍

### 包含
- `VoiceInputApp._process_speech`：改為注入 JS 建立 `webkitSpeechRecognition`（`lang='zh-HK'`）→ `start()` → 輪詢 `window.__voiceResult`（事件驅動結果）。
- `VoiceInputApp._get_current_text`：刪除（被 `onresult` 取代）。
- 錯誤事件 → 狀態列文案映射（`no-speech` / `not-allowed` / `network` / `aborted`）。
- 保留 `_initialize_driver`、`_setup_permissions`（`audioCapture` 授權）、`_ensure_driver_alive`、熱鍵、托盤、剪貼簿開關、音效、`reset_timer` 全部現有行為。
- 新增「識別流程契約測試」，並確保既有 `tests/test_merge_contract.py` 仍全 PASS。

### 不包含
- 不抽共用模組（維持 single-file monolith）。
- 不改 UI / 熱鍵設定 / 托盤 / 剪貼簿開關行為。
- 不新增外部依賴。
- 不導入正式 Google Speech-to-Text API；不做離線識別。

## 技術決策

### 觸發方式：JS `start()` + Selenium 輪詢 `window.__voiceResult`

選擇「注入 JS 建立識別並 `start()`，Selenium 以固定間隔輪詢結果變數」而非 `execute_async_script`：
- 可自然搭配既有 `stop_event`（再次觸發即中斷目前辨識），維持「再按一次熱鍵＝停止」的現有語義。
- 與目前程式「背景執行緒 + 輪詢」的既有風格一致，改動面最小。
- 每個 session 前先 `reset` 結果變數，避免殘留上一輪結果。

### 仍載入 `google.com.hk?hl=zh-HK`
- `webkitSpeechRecognition` 需在 HTTPS 且有語音服務的 Google 域上執行；此域已透過 `_setup_permissions` 授權 `audioCapture`。
- 不更改 `_initialize_driver` 的任何參數。

## 元件變更

### `VoiceInputApp._process_speech`（核心改動）

新流程：

```text
play_sound("start") → ui_queue.put(LISTENING)
載入 https://www.google.com.hk/webhp?hl=zh-HK
若 stop_event 已設定 → 返回
execute_script: reset __voiceResult → 建立 webkitSpeechRecognition(lang='zh-HK')
              → 接 onresult/onerror/onend → start()
以 0.2s 間隔輪詢 window.__voiceResult，直到 done 或 stop_event
成功 → play_sound("success")
     → copy_to_clipboard 時 put(("CLIPBOARD", text))
     → put(("IDLE", 顯示, 綠)) → kb_controller.type(text)
無結果 → put(("IDLE", 對應錯誤文案, 色))
finally: is_processing=False、stop_event.clear()、啟動 3 秒 reset_timer
```

### 注入頁面的 JS（示意）

```js
window.__voiceResult = { done: false, transcript: '', error: '' };
var rec = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
rec.lang = 'zh-HK';
rec.interimResults = false;
rec.maxAlternatives = 1;
rec.onresult = function (e) {
  var t = ''; for (var i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
  window.__voiceResult = { done: true, transcript: t, error: '' };
};
rec.onerror = function (e) {
  window.__voiceResult = { done: true, transcript: '', error: e.error };
};
rec.onend = function () {
  if (!window.__voiceResult.done) window.__voiceResult = { done: true, transcript: '', error: 'no-speech' };
};
rec.start();
```

- 輪詢時同時檢查 `stop_event`；被中斷時直接結束 session（不等待）。
- 辨識 session 有天然靜音超時（約 10 秒內），因此「無聲 → `onend` → 判 `no-speech`」可自然閉環，不需額外計時器。

### 刪除 `VoiceInputApp._get_current_text` 與 `is_garbage_token`
- `is_garbage_token`（`main.pyw:68`）只被 `_get_current_text`（`main.pyw:682`）使用；`_get_current_text` 刪除後即無任何呼叫者，一併刪除。

## 錯誤處理對映

| JS `onerror` error | 狀態列顯示 | 顏色 |
|---|---|---|
| `no-speech` | ⚠️ 未聽清 | `#c19c00`（黃，沿用） |
| `not-allowed` / `service-not-allowed` | ❌ 麥克風權限被拒 | `#d13438`（紅） |
| `network` | ❌ 無法連線識別 | `#d13438`（紅） |
| `aborted`（使用者中斷） | 不提示，回原樣 | — |
| 其他 | ⚠️ 識別失敗 | `#c19c00` |

成功流程（音效、剪貼簿、狀態、打字）與現行完全一致，不變。

## 資料流

```text
觸發語音 → _process_speech（背景執行緒）
  → 載入 google.com.hk → 注入識別 + start()
  → 輪詢 window.__voiceResult（0.2s，尊重 stop_event）
  → onresult 拿到文字（或 error / no-speech）
  → 成功: 音效 → 剪貼簿(若開) → 狀態列 → 打字
  → 失敗: 對應錯誤文案
  → finally: 重置狀態 + 3 秒後狀態列回預設
```

## 相容性與限制

- 依賴 Chrome 內建 Web Speech API（已實測 Chrome 151 可用）。
- 仍需 Windows + Chrome + 真實麥克風 + 網路；本質仍是免費蹭 Google 網頁語音。
- 不再讀 `name=q`，故結果落點由 `onresult` 事件保證；不依賴任何 Google 網頁結構。
- 本規格不承諾在本環境完成 Chrome/麥克風整合測試（環境沙箱限制）；已由 Spike 真機驗證核心可行性。

## 測試

### 保留
- `tests/test_merge_contract.py`：5 個剪貼簿契約測試維持全 PASS。

### 新增（同風格，純文字檢查 `main.pyw`）
- `_process_speech` 含有 `webkitSpeechRecognition` 與 `onresult`（事件驅動取結果）。
- 含 `window.__voiceResult` 結果變數。
- **不含** `element_to_be_clickable`（防止打回「點 Google 按鈕」）。
- `_get_current_text` / `By.NAME, "q"` 不再存在（或已無使用）。

## 驗證

- `python -m py_compile main.pyw` 無輸出、回傳碼 0。
- `python -m pytest tests/ -q`：既有 + 新增全部 PASS。
- `git diff --check` 無輸出。
- 真機手動驗證（使用者執行）：啟動後講粵語，狀態列顯示成功、文字自動輸入、剪貼簿開關正常。
