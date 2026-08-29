# 粵語語音輸入法

[![Latest Release](https://img.shields.io/badge/version-v2.1-green?style=flat&logo=github)](https://github.com/shamough1792/CantoneseVoiceInput/releases/tag/v2.1)
[![Python](https://img.shields.io/badge/python-3.8+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
![License](https://img.shields.io/badge/license-MIT-orange?style=flat)

基於 Chrome 語音識別技術開發的輕量化桌面粵語語音輸入工具。支援浮動卡片介面、動態熱鍵設定、自動打字輸入。

專案提供單一入口 `main.pyw`：辨識成功後自動輸入到目前游標位置。
在設定視窗中可勾選「辨識後自動複製到剪貼簿」，勾選後辨識成功會同時複製到系統剪貼簿。

## ✨ 功能特點

- 🎤 **語音輸入** — 按下 `Ctrl+Alt+V` 或點擊麥克風開始識別
- 💬 **懸浮卡片** — 膠囊式設計，不佔工作空間，隨意拖動
- ⌨️ **自動輸入** — 識別的文字直接打到游標位置
- 🗂️ **系統托盤** — 後台運行，點擊托盤圖標可快速顯示/隱藏
- 🔧 **動態熱鍵** — 在 UI 內自訂快捷鍵組合
- 🔌 **即插即用** — 下載即用，無需額外配置

## 🚀 快速開始

### 下載執行

1. 從 [Releases](https://github.com/shamough1792/CantoneseVoiceInput/releases) 下載最新 `CantoneseVoiceInput.exe`
2. 雙擊執行（無需安裝）
3. 允許麥克風權限提示

### 首次使用

1. 程式啟動後在右下角顯示懸浮工具欄
2. 點擊 🎙️ 或按 `Ctrl+Alt+V` 開始錄音
3. 清晰地說出廣東話
4. 識別結果自動輸入到游標位置

## 🎮 操作指南

| 操作 | 方法 |
|------|------|
| 開始/停止錄音 | 點擊 🎙️ 按鈕 或 按 `Ctrl+Alt+V` |
| 自訂熱鍵 | 點擊 ⚙️ 設定按鈕，按下新組合鍵 |
| 查看幫助 | 點擊 ❓ 按鈕 |
| 隱藏卡片 | 點擊 ✕ 按鈕（自動最小化至托盤） |
| 恢復卡片 | 點擊系統托盤麥克風圖標 |
| 退出程式 | 右鍵托盤圖標 → 「退出程式」 |
| 移動卡片位置 | 拖動卡片標題欄到任意位置 |

## 🛠️ 系統需求

| 項目 | 要求 |
|------|------|
| **作業系統** | Windows 10/11 64-bit |
| **Chrome** | 已安裝並版本 >= 90 |
| **麥克風** | 可正常使用的裝置 |
| **網絡** | 需要網絡連線（用於語音識別） |
| **記憶體** | 建議 2GB 以上 |

## 📦 從源碼構建

適合開發者或想自訂功能的用戶。

### 1. 環境準備

確保已安裝 Python 3.8+，然後安裝依賴：

**快速安裝（推薦）**
```bash
# Windows 用戶雙擊
install.bat
```

**手動安裝**
```bash
pip install -r requirements.txt
```

依賴說明：
| 套件 | 版本 | 用途 |
|------|------|------|
| `selenium` | >=4.0.0 | Web 自動化引擎 |
| `pynput` | >=1.7.6 | 全局熱鍵監聽 + 鍵盤輸入模擬 |
| `pystray` | >=0.19.5 | 系統托盤功能 |
| `Pillow` | >=9.0.0 | 托盤圖示生成 |
| `PyInstaller` | >=5.0 | 打包成 `.exe` |
| `webdriver-manager` | >=3.8.0 | **自動管理 Chrome Driver**（新增優化） |

> ⚡ **`webdriver-manager` 優勢** — 自動偵測 Chrome 版本並下載相應 Driver，無需手動配置驅動版本對應關係，解決版本失配問題。

### 2. 準備資源

將 `app.ico` 放至專案根目錄（已包含在源碼中）。

### 3. 打包成 EXE

使用專案內的 `main.spec`（已設定好提示音資源、圖示與打包參數）：

```bash
pyinstaller main.spec --noconfirm
```

> 💡 `main.spec` 已包含：`--onefile`（單一執行檔）、`--windowed`（隱藏控制台）、`--hidden-import=selenium.webdriver.chrome.webdriver`（確保 Selenium 模組載入）、`-i app.ico`（應用圖示）、以及 `res/*.wav` 提示音資源打包。

**如偏好直接單行指令**（需手動加上音效資源）：

```bash
pyinstaller --noconfirm --onefile --windowed --hidden-import=selenium.webdriver.chrome.webdriver -i app.ico --add-data "res;res" main.pyw
```

**參數說明**
- `--onefile` — 打包為單一 `.exe` 檔（首次運行會解壓到臨時目錄）
- `--windowed` — 隱藏 CMD 控制台視窗
- `--hidden-import=selenium.webdriver.chrome.webdriver` — 確保 Selenium 內部模組正確載入
- `-i app.ico` — 設定應用圖示
- `--add-data "res;res"` — 將提示音資源資料夾一併打包（Windows 用分號 `;` 分隔）

生成的 `.exe` 位於 `dist/` 資料夾。

## 🔧 疑難排解

| 問題 | 解決方案 |
|------|--------|
| **「Chrome 驅動版本不符」** | 自動處理：`webdriver-manager` 已集成，無需手動下載 |
| **「麥克風無法錄音」** | 檢查系統設定 → 隱私 → 麥克風，確保應用有權限；或重啟 Chrome 程序 |
| **「Chrome 程序異常」** | 應用會自動偵測並重啟 Chrome（v1.5+ 新增） |
| **「語音識別無反應」** | 確認網絡連線正常；檢查系統設定 → 隱私 → 麥克風權限是否允許；或重啟應用 |
| **「卡片卡頓或閃爍」** | 嘗試重啟應用或更新 Chrome 瀏覽器 |

## 🧰 維護與診斷

新增維護工具 `tools/spike_realmic.py`：當 Chrome/Google 改版導致識別異常時，可用來快速診斷語音通道是否正常。

```bash
python tools/spike_realmic.py
```

在一般桌面視窗執行，並對麥克風說一句粵語。若成功印出識別文字，代表語音通道正常，問題應在程式邏輯；若出現 `no-speech`、`network` 等錯誤，則可能是 Chrome/Google、權限或網路問題。

## 📋 技術棧

- **GUI** — Tkinter（原生 Windows 介面）
- **語音識別** — Chrome Web Speech API（`webkitSpeechRecognition`，直接呼叫、事件驅動，v1.6+）
- **自動化** — Selenium + Chrome WebDriver（頁面載入與麥克風權限管理）
- **系統整合** — pynput（全局熱鍵）、pystray（托盤）、ctypes（Windows API）
- **輸入模擬** — pynput KeyboardController
- **打包** — PyInstaller
- **驅動管理** — webdriver-manager ✨

## 📄 授權

本專案採用 [MIT License](LICENSE) 開源。

---

**貢獻** — 歡迎提交 Issue 或 Pull Request！  
**反饋** — 如遇任何問題，請在 [GitHub Issues](https://github.com/shamough1792/CantoneseVoiceInput/issues) 回報。
