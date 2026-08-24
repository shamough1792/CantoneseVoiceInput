# 粵語語音輸入法

<br>

[![Latest Release](https://img.shields.io/badge/version-v1.5-green?style=flat&logo=github)](https://github.com/shamough1792/CantoneseVoiceInput/releases/tag/v1.5)
[![Python](https://img.shields.io/badge/python-3.8+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
![License](https://img.shields.io/badge/license-MIT-orange?style=flat)

<br>

基於 Chrome 語音識別技術開發的輕量化桌面粵語語音輸入工具。支援浮動卡片介面、動態熱鍵設定、自動打字輸入。

<br>

## ✨ 功能特點

<br>

- **語音輸入**：按下 `Ctrl+Alt+V` 或點擊麥克風圖標開始語音識別
- **懸浮界面**：膠囊式設計，不佔用工作空間
- **自動貼上**：識別的文字自動貼上到當前游標位置
- **系統托盤**：從托盤圖標隨時顯示/隱藏
- **拖動定位**：可隨意拖動懸浮欄到螢幕任何位置
- **背景運行**：最小化至系統托盤，不干擾工作
  
<br>

## 🚀 快速開始

<br>

### 下載安裝
1. 從 [Releases](https://github.com/shamough1792/CantoneseVoiceInput/releases) 下載最新 `CantoneseVoiceInput.exe`
2. 直接執行（無需安裝）

<br>

### 首次使用
- 程式啟動後會顯示懸浮工具欄
- 點擊 🎙️ 或按 `Ctrl+Alt+V` 開始語音輸入
- 清晰地說出廣東話
- 識別的文字會自動出現在當前游標位置

<br>

## 🎮 操作指南

<br>

| 操作 | 方法 |
|------|------|
| 開始/停止錄音 | 點擊 🎙️ 按鈕或按 `Ctrl+Alt+V` |
| 隱藏至托盤 | 點擊 ✕ 按鈕 |
| 從托盤顯示 | 點擊系統托盤圖標 |
| 退出程式 | 右鍵托盤圖標 → 「退出程式」 |
| 移動位置 | 拖動懸浮欄任意位置 |

<br>

## 🛠️ 系統需求

<br>

- **作業系統**：Windows 10/11
- **瀏覽器**：Google Chrome（語音識別需要）
- **麥克風**：可正常使用的麥克風
- **網絡**：需要網絡連線進行語音處理

<br>

## 🛠️ 開發與建構 (Building from Source)

<br>

如果你希望從原始碼自行編譯打包成獨立的 `.exe` 執行檔，請依照以下步驟操作：

### 1. 安裝依賴套件
確保已安裝 Python 3.8+，並執行以下指令安裝所需庫：

```bash
pip install selenium pynput pystray pillow PyInstaller
```

<br>

### 2. 準備圖示檔
將專案所需的圖示檔案 app.ico 放至專案根目錄下。

<br>

### 3. 執行 PyInstaller 打包
使用以下指令進行單一檔案（One-file）及無控制台視窗（Windowed）的編譯打包：

```bash
pyinstaller --noconfirm --onefile --windowed --hidden-import=selenium.webdriver.chrome.webdriver -i app.ico main.pyw
```

<br>

說明：

--onefile：將所有依賴打包為單一 .exe 檔。

--windowed：隱藏 CMD 主控台視窗。

--hidden-import=selenium.webdriver.chrome.webdriver：確保 Selenium Chrome Driver 正確載入。

-i app.ico：指定產出的應用程式圖示。

編譯完成後，產生的執行檔將存放在 dist/ 資料夾中。


<br>

## 📄 授權 (License)

<br>

本專案採用 [MIT License](LICENSE) 開源。
