# Google 風格提示音 設計規格

**日期：** 2026-08-29
**範圍：** 將 `main.pyw` 的三種提示音（開始聆聽 / 辨識成功 / 辨識失敗）從 `winsound.Beep` 方波改為**真實下載的 Google 風格提示音 WAV**（`res/snd_*.wav`），內嵌進專案與打包檔。

## 目標

1. 音質從「方波硬聲」提升為真實的 Google 語音輸入聽感。
2. 使用使用者下載的免授權提示音（`snd_start.mp3` / `snd_success.mp3` / `snd_fail.mp3`），以 ffmpeg 轉成 WAV 後內嵌。
3. 零外部依賴：只用 Python 標準庫 `winsound` 播放，不新增任何套件。
4. 維持既有呼叫端契約：`play_sound(sound_type)` 簽名不變，三種 `start` / `success` / `fail` 行為語義不變。

## 音效來源

- 使用者自 Mixkit / Pixabay 等免授權站點下載，放入 `res/`：
  - `res/snd_start.mp3`（17656 B，0.53s，44100Hz 立體聲）
  - `res/snd_success.mp3`（21411 B，0.76s）
  - `res/snd_fail.mp3`（25164 B，1.00s）
- 以 ffmpeg 轉為 **44100Hz / 16-bit / mono WAV**（`winsound.PlaySound` 支援 WAV 檔路徑）：
  - `res/snd_start.wav`、`res/snd_success.wav`、`res/snd_fail.wav`

## 技術實作

### 播放方式
- `winsound.PlaySound(path, winsound.SND_FILENAME)` 播放 WAV 檔。
- 資源路徑解析：`_resource_path()` 處理 PyInstaller 凍結後 `sys._MEIPASS` 與一般執行根目錄兩種情況。
- 背景 daemon thread 播放，不阻塞 UI / 語音處理。
- 播放失敗（檔案缺、格式不支援）靜默。

### 三種音效對應
```python
SOUND_FILES = {
    "start":   "res/snd_start.wav",
    "success": "res/snd_success.wav",
    "fail":    "res/snd_fail.wav",
}
```

## 元件變更

### `main.pyw`
- 移除上一版的合成函數 `_make_tone` / `_make_duotone_wav`、`SAMPLE_RATE`、`math` / `struct` / `io` / `wave` import。
- 新增 `_resource_path()`、`SOUND_FILES`、`_play_wav()`。
- `play_sound()` 改為查表播放對應 WAV。

### `main.spec`
- `datas` 加入三個 WAV（`('res/snd_*.wav', 'res')`），確保打包進 `.exe` 的 `_MEIPASS`。

### `res/`
- 新增 `snd_start.mp3` / `snd_success.mp3` / `snd_fail.mp3`（原始下載）與對應 `.wav`（ffmpeg 轉換）。

### 呼叫端（不變）
`_process_speech`（`start` / `success` / `fail`）呼叫位置與參數完全不動。

## 測試

- 既有 11 個契約測試應全 PASS。
- `python -m py_compile main.pyw` 應 exit 0。
- 真機驗證：實際講一句話聽三種音效是否如預期。

## 不包含

- 不抽共用模組（維持 single-file monolith）。
- 不引入 MP3 解碼套件（僅 WAV 內嵌）。
- 不改變 UI、熱鍵、托盤、語音辨識邏輯。
