"""
真機驗證腳本：驗證「直接呼叫 webkitSpeechRecognition」能不能在真實麥克風下
把粵語講話轉成文字（onresult 事件確實返回 transcript）。

有別於 spike_scheme_c.py：此腳本【不使用假音訊裝置】，改用你的真實麥克風。
流程：載入 google.com.hk → 授權麥克風 → 直接 start() → 你講粵語 → 印出 transcript。

執行方式（在你自己的桌面視窗，別在受限沙箱跑）：
    python spike_realmic.py
腳本會印出「請開始講粵語…」，你有約 15 秒時間講一句，例如「今日天氣好好」。
"""
import sys
import time
import json
import tempfile
import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://www.google.com.hk/webhp?hl=zh-HK"

INSTALL_AND_START = r"""
window.__spike = { phase: 'init', transcript: '', error: '', events: [] };
(function () {
  try {
    var rec = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    rec.lang = 'zh-HK';
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.continuous = false;
    rec.onstart = function () { __spike.phase = 'started'; __spike.events.push('onstart'); };
    rec.onerror = function (e) { __spike.phase = 'error'; __spike.error = e.error; __spike.events.push('onerror:' + e.error); };
    rec.onresult = function (e) {
      var t = '';
      for (var i = 0; i < e.results.length; i++) {
        if (e.results[i].length) t += e.results[i][0].transcript;
      }
      __spike.phase = 'result';
      __spike.transcript = t;
      __spike.events.push('onresult:' + t);
    };
    rec.onend = function () {
      __spike.events.push('onend');
      if (__spike.phase !== 'result') __spike.phase = 'ended-no-result';
    };
    rec.start();
    __spike.events.push('called-start-no-throw');
  } catch (err) {
    __spike.phase = 'threw'; __spike.error = String(err); __spike.events.push('throw:' + err);
  }
})();
"""

READ_JS = "return window.__spike;"


def build_driver():
    opts = Options()
    opts.add_argument(f"--app={URL}")
    opts.add_argument("--window-position=-32000,-32000")
    opts.add_argument("--window-size=1,1")
    opts.add_argument("--lang=zh-HK")
    # 只「自動接受權限彈窗」，不塞假音訊 → 使用真實麥克風
    opts.add_argument("--use-fake-ui-for-media-stream")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--user-data-dir=" + os.path.join(tempfile.gettempdir(), "spike_cvi_realmic_userdata"))
    try:
        service = Service(ChromeDriverManager().install())
    except Exception as e:
        print(f"[driver] webdriver-manager 失敗: {e}，改用快取", flush=True)
        cached = os.path.expandvars(r"%USERPROFILE%\.wdm\drivers\chromedriver\win64\151.0.7922.138\chromedriver-win64\chromedriver.exe")
        service = Service(cached) if os.path.exists(cached) else Service()
    return webdriver.Chrome(service=service, options=opts)


def main():
    driver = build_driver()
    print("[OK] 隱藏 Chrome 已啟動（麥克風已自動授權）", flush=True)
    try:
        try:
            driver.execute_cdp_cmd("Browser.grantPermissions", {
                "origin": "https://www.google.com.hk",
                "permissions": ["audioCapture"]
            })
            print("[OK] 麥克風權限已授予", flush=True)
        except Exception as e:
            print(f"[警告] 授權失敗(非致命): {e}", flush=True)

        time.sleep(0.5)
        driver.execute_script(INSTALL_AND_START)
        time.sleep(0.5)

        print("\n🎙️  請現在開始講一句粵語（約 15 秒），例如：「今日天氣好唔好」。", flush=True)
        deadline = time.time() + 18
        state = driver.execute_script(READ_JS)
        while time.time() < deadline:
            state = driver.execute_script(READ_JS)
            if state.get("phase") == "result":
                break
            if state.get("phase") in ("threw",) :
                break
            time.sleep(0.3)

        print("\n===== 結果 =====", flush=True)
        print(json.dumps(state, ensure_ascii=False, indent=2), flush=True)
        if state.get("phase") == "result" and state.get("transcript"):
            print(f"\n✅ 識別到粵語文字: 「{state['transcript']}」", flush=True)
        elif state.get("error") in ("no-speech", "aborted"):
            print("\n⚠️  沒有錄到語音（no-speech）。請確認：這是一般桌面視窗、非受限環境，且麥克風有通。", flush=True)
        elif state.get("phase") == "threw":
            print("\n❌ 呼叫時拋例外:", state.get("error"), flush=True)
        else:
            print("\n⚠️  未取得結果。事件:", state.get("events"), flush=True)
        return state
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    r = main()
    tmp = os.path.join(tempfile.gettempdir(), "spike_realmic_result.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print(f"\n[結果已存] {tmp}", flush=True)
    sys.exit(0)