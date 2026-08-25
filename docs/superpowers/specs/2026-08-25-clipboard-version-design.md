# 獨立剪貼簿版本設計規格

- 日期：2026-08-25
- 範圍：建立 `main_2.pyw` 的獨立剪貼簿版本並更新 `README.md`

## 目標

保留現有 `main.pyw` 的行為不變，讓 `main_2.pyw` 成為另一個可獨立啟動的版本。辨識成功後，`main_2.pyw` 必須同時：

1. 將辨識文字寫入 Tkinter 系統剪貼簿。
2. 將辨識文字模擬輸入到目前游標位置。

## 檔案範圍

- 修改 `main_2.pyw`：保留其獨立入口，整合目前 `main.pyw` 已有的 ChromeDriver 自動管理與相關初始化方式，並保留剪貼簿輸出。
- 不修改 `main.pyw`：維持原有僅自動輸入的版本。
- 修改 `README.md`：說明兩個版本的差異、啟動方式、輸出行為及剪貼簿注意事項。
- 不新增外部依賴；Tkinter 剪貼簿 API 已由 Python 標準庫提供。

## 行為與資料流

`main_2.pyw` 的語音辨識流程與現有版本相同：Google 香港語音搜尋取得結果後，背景執行緒將狀態放入 `ui_queue`。

成功取得 `recognized_text` 後：

1. 將 `("CLIPBOARD", recognized_text)` 放入 `ui_queue`。
2. 將成功狀態訊息放入 `ui_queue`。
3. 使用 `KeyboardController.type(recognized_text)` 輸入目前游標位置。
4. Tkinter 主執行緒在 `_check_queue()` 收到 `CLIPBOARD` 訊息後，以 `clipboard_clear()`、`clipboard_append()` 和 `update()` 更新系統剪貼簿。

剪貼簿操作失敗時只記錄錯誤，不應阻止自動輸入流程或讓整個辨識 worker 崩潰。

## 版本差異

| 入口 | 辨識成功後行為 |
|---|---|
| `main.pyw` | 自動輸入到目前游標位置 |
| `main_2.pyw` | 複製到系統剪貼簿，並自動輸入到目前游標位置 |

兩個版本都需要 Windows、Chrome、可用麥克風及網路連線；兩者共用相同的 Python 依賴。

## 相容性與限制

- `main_2.pyw` 仍依賴 Tkinter 的系統剪貼簿；程式結束後，剪貼簿內容是否繼續存在取決於 Windows/Tk 的剪貼簿管理行為。
- 自動輸入仍依賴目前的前景視窗與輸入焦點。
- 不將剪貼簿功能做成可切換設定，避免改變兩個獨立入口的語意。
- 不在本次工作中重構共用模組，也不修改既有 UI、熱鍵或語音辨識流程。

## 驗證

- 執行 `python -m py_compile main.pyw main_2.pyw`。
- 確認 `main.pyw` 沒有未預期的差異。
- 以文字搜尋確認 `main_2.pyw` 包含剪貼簿佇列處理與成功辨識後的剪貼簿通知。
- 檢查 README 已描述兩個版本及同時輸出的行為。
- 不在目前環境宣稱已完成實際 Chrome、麥克風或 GUI 整合測試。
