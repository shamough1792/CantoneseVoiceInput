# 平滑按鈕與剪貼簿開關實作計畫

**目標：** 沿用 Tkinter 架構改善圓角鋸齒，將剪貼簿勾選框改為深淺模式一致的開關。
**已確認設計：** 自訂抗鋸齒控制項，並非 WinUI 原生元件；不遷移介面框架。
**架構：** 使用現有 Pillow 在四倍解析度繪製圓角表面，再以 LANCZOS 縮小；文字仍由 Tk 繪製。開關保留 BooleanVar 與既有設定 setter。
**技術棧：** Python、Tkinter、Pillow、pytest。延續既有隔離 worktree，不提交、合併或打包。

## 檔案與責任

- `main.pyw`：共用 `_rounded_surface`、`RoundedButton`、`ToggleSwitch`、麥克風底圈與主題接線。
- `tests/test_theme_behavior.py`：擴充既有 AST 載入器，保留不啟動瀏覽器及全域熱鍵的隔離方式。
- `tests/test_smooth_controls.py`：像素抗鋸齒、按鈕點擊與鍵盤互動、開關儲存及主題回歸。
- `tests/conftest.py`：共用真正的 Tk 直譯器，各 UI 測試仍各自建立獨立 Toplevel，避免重複初始化造成腳本讀取失敗。
- `tests/test_merge_contract.py`：將已淘汰的 Checkbutton 契約更新為 ToggleSwitch。

## 執行步驟

- [x] 新增回歸測試，舊實作七項因缺少平滑表面或開關而失敗。
- [x] 新增 RGBA 圓角繪圖，檢查透明角落、實心中央及半透明過渡像素。
- [x] 按鈕改用保留引用的 `ImageTk.PhotoImage`，處理懸停、按下、移出取消、鍵盤操作，保留 `config` 與 `_invoke` 契約。
- [x] 麥克風底圈沿用相同抗鋸齒繪圖，保留錄音狀態與圖示。
- [x] 將剪貼簿選項換成膠囊開關；整列可點擊，Space／Enter 可操作，變更沿用 `set_copy_to_clipboard`，銷毀時移除變數 trace。
- [x] 保留既有 Pillow 最低版本相容性；相容測試先因缺少 `Resampling` 失敗，再通過。
- [x] 最終完整測試 35 項通過，語法與差異檢查通過；已檢視深淺模式的實際截圖。

## 驗收界線

- 不更動語音辨識、全域快捷鍵、視窗單例與 Windows 11 原生外框圓角。
- 不增加第三方依賴，不修改使用者實際設定檔。
- 不宣稱為 WinUI 原生按鈕，不宣稱已驗證所有 DPI 或舊版 Windows。
