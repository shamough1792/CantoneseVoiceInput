"""以隔離設定與真正 Tk 元件驗證主題，不啟動瀏覽器或全域熱鍵。"""
import ast
import ctypes
import json
import os
from pathlib import Path
import queue
from types import SimpleNamespace
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk


def load_ui_namespace():
    source = Path(__file__).resolve().parents[1] / "main.pyw"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"THEME_PALETTES", "DEFAULT_CONFIG", "CONFIG_DIR", "COLOR_BG",
             "COLOR_BORDER", "COLOR_ACCENT", "COLOR_ICON", "COLOR_MIC_BG",
             "COLOR_MIC_ACTIVE", "COLOR_SURFACE", "COLOR_MUTED"}
    definitions = {"normalize_theme", "load_config", "save_config",
                   "RoundedButton", "ToggleSwitch", "_rounded_surface",
                   "CardVoiceUI", "_apply_rounded_window"}
    nodes = [node for node in tree.body if
             isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in definitions
             or isinstance(node, ast.Assign) and any(
                 isinstance(target, ast.Name) and target.id in names for target in node.targets)]
    namespace = {"tk": tk, "ctypes": ctypes, "os": os, "json": json,
                 "Image": Image, "ImageDraw": ImageDraw, "ImageTk": ImageTk}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


def test_theme_config_preserves_both_preferences(tmp_path):
    ns = load_ui_namespace()
    ns["CONFIG_DIR"] = str(tmp_path)
    assert ns["load_config"]()["theme"] == "dark"
    ns["save_config"]({"copy_to_clipboard": True})
    ns["save_config"]({"theme": "light"})
    assert ns["load_config"]() == {"copy_to_clipboard": True, "theme": "light"}
    ns["save_config"]({"copy_to_clipboard": False})
    assert ns["load_config"]()["theme"] == "light"
    for invalid in (None, [], {}, 42, "unknown"):
        assert ns["normalize_theme"](invalid) == "dark"


def test_real_windows_switch_together_and_buttons_fit(tk_window):
    ns = load_ui_namespace()
    hotkeys = SimpleNamespace(get_display_text=lambda: "CTRL+ALT+V", _start_listener=lambda: None,
                              stop_listener=lambda: None)
    app = SimpleNamespace(theme="dark", copy_to_clipboard=False)
    ui = ns["CardVoiceUI"](queue.Queue(), lambda: None, hotkeys, app)
    app.set_theme = lambda theme: ui.apply_theme(theme)
    app.set_copy_to_clipboard = lambda value: None
    ns["keyboard"] = SimpleNamespace(Listener=lambda **kwargs: SimpleNamespace(start=lambda: None, stop=lambda: None))
    try:
        ui.start()
        ui._open_settings_dialog()
        ui.apply_theme("light")
        ui.root.update()
        ui._show_help()
        ui.root.update()
        settings, help_window = ui.settings_dialog, ui.help_dialog
        assert help_window.cget("bg") == ns["THEME_PALETTES"]["light"]["bg"]
        record = next(widget for widget, _, _ in ui._theme_bindings[settings]
                      if isinstance(widget, ns["RoundedButton"]) and widget._text == "CTRL+ALT+V")
        record._invoke()
        ui._draw_mic_button(active=True)
        for theme in ("light", "dark", "light"):
            assert ui.apply_theme(theme)
            ui.root.update()
            palette = ns["THEME_PALETTES"][theme]
            assert settings.cget("bg") == palette["bg"]
            assert help_window.cget("bg") == palette["bg"]
            assert ui.status_label.cget("bg") == palette["bg"]
            assert ui._mic_active
            assert ui._theme_buttons[theme]._button_bg == palette["accent"]
            assert record._text == "請按下組合鍵..."
            record.event_generate("<Enter>")
            record.event_generate("<Leave>")
            assert record._button_fg == palette["warning"]
        record._invoke()
        assert record._text == "CTRL+ALT+V"
        ui._open_settings_dialog()
        ui._show_help()
        assert ui.settings_dialog is settings and ui.help_dialog is help_window
        for window in (settings, help_window):
            for widget, _, _ in ui._theme_bindings[window]:
                if isinstance(widget, ns["RoundedButton"]):
                    assert widget.winfo_height() >= widget._button_height
                    assert widget.winfo_width() >= widget._button_width
                    assert widget.winfo_rooty() + widget.winfo_height() <= window.winfo_rooty() + window.winfo_height()
        settings.destroy()
        ui.apply_theme("dark")
        ui.root.update()
        assert settings not in ui._theme_bindings
    finally:
        if ui.root is not None:
            ui.root.destroy()
