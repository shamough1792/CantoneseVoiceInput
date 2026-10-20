"""以像素及真正 Tk 元件驗證平滑外觀，設定僅寫入暫存目錄。"""
import ast
from pathlib import Path
import queue
from types import SimpleNamespace
import tkinter as tk

import pytest

from test_theme_behavior import load_ui_namespace


@pytest.mark.parametrize("size,radius", [((150, 34), 10), ((284, 42), 12), ((44, 24), 12)])
def test_rounded_surface_has_transparent_corners_and_antialiased_edges(size, radius):
    ns = load_ui_namespace()
    assert "_rounded_surface" in ns, "尚未使用抗鋸齒圓角表面"
    image = ns["_rounded_surface"](*size, radius, "#ffffff")
    assert image.size == size
    assert image.mode == "RGBA"
    alpha = image.getchannel("A")
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((size[0] // 2, size[1] // 2)) == 255
    assert any(0 < value < 255 for value in alpha.getdata())
    assert alpha.getpixel((0, radius)) > 240


def test_rounded_surface_supports_legacy_pillow_resampling_names():
    ns = load_ui_namespace()
    image_module = ns["Image"]
    # 模擬既有最低版本只提供 LANCZOS 常數，仍使用真正 Pillow 繪圖與縮放。
    ns["Image"] = SimpleNamespace(new=image_module.new, LANCZOS=1)
    image = ns["_rounded_surface"](44, 24, 12, "#ffffff")
    assert image.size == (44, 24)
    assert any(0 < value < 255 for value in image.getchannel("A").getdata())


def test_button_uses_image_and_preserves_interaction_after_repaint(tk_window):
    ns = load_ui_namespace()
    root = tk_window()
    calls = []
    try:
        button = ns["RoundedButton"](root, text="重設快捷鍵", width=150, height=36,
                                     command=lambda: calls.append("click"))
        button.pack()
        root.update()
        assert [button.type(item) for item in button.find_all()].count("image") == 1
        assert not any(button.type(item) == "oval" for item in button.find_all())
        normal = button._background_image
        button.event_generate("<Enter>")
        assert button._background_image is not normal
        button.event_generate("<ButtonPress-1>", x=15, y=15)
        assert calls == []
        button.event_generate("<ButtonRelease-1>", x=15, y=15)
        assert calls == ["click"]
        button.event_generate("<ButtonPress-1>", x=15, y=15)
        button.event_generate("<Leave>")
        button.event_generate("<ButtonRelease-1>", x=-2, y=-2)
        assert calls == ["click"]
        button.config(text="已設定", bg="#ffffff", fg="#087f70")
        root.configure(bg="#f3f3f3")
        button.config(bg="#ffffff")
        assert button._text == "已設定"
        assert button.cget("bg") == "#f3f3f3"
        button.focus_force()
        root.update()
        button.event_generate("<KeyPress-space>")
        button.event_generate("<KeyRelease-space>")
        assert calls == ["click", "click"]
    finally:
        root.destroy()


def test_toggle_tracks_variable_and_keyboard_without_duplicate_callbacks(tk_window):
    ns = load_ui_namespace()
    assert "ToggleSwitch" in ns, "剪貼簿選項仍是舊式勾選框"
    root = tk_window()
    value = tk.BooleanVar(root, value=False)
    calls = []
    try:
        switch = ns["ToggleSwitch"](root, text="自動複製到剪貼簿", variable=value,
                                    palette=ns["THEME_PALETTES"]["dark"],
                                    command=lambda: calls.append(value.get()))
        switch.pack(fill="x")
        root.update()
        switch.event_generate("<ButtonPress-1>", x=10, y=15)
        switch.event_generate("<ButtonRelease-1>", x=10, y=15)
        assert value.get() and calls == [True]
        value.set(False)
        root.update()
        assert calls == [True]
        switch.focus_force()
        root.update()
        switch.event_generate("<KeyPress-space>")
        switch.event_generate("<KeyRelease-space>")
        assert value.get() and calls == [True, True]
        switch.event_generate("<KeyPress-Return>")
        switch.event_generate("<KeyRelease-Return>")
        assert not value.get() and calls == [True, True, False]
        switch.destroy()
        assert value.trace_info() == []
        value.set(True)
    finally:
        root.destroy()


def test_clipboard_switch_keeps_saved_value_and_theme_when_reopened(tk_window, tmp_path):
    ns = load_ui_namespace()
    assert "ToggleSwitch" in ns, "設定視窗尚未接上膠囊開關"
    ns["CONFIG_DIR"] = str(tmp_path)
    tree = ast.parse((Path(__file__).resolve().parents[1] / "main.pyw").read_text(encoding="utf-8"))
    app_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "VoiceInputApp")
    setter = next(node for node in app_class.body if isinstance(node, ast.FunctionDef) and node.name == "set_copy_to_clipboard")
    exec(compile(ast.Module(body=[setter], type_ignores=[]), "main.pyw", "exec"), ns)
    app = SimpleNamespace(theme="dark", copy_to_clipboard=False)
    app.set_copy_to_clipboard = lambda value: ns["set_copy_to_clipboard"](app, value)
    hotkeys = SimpleNamespace(get_display_text=lambda: "CTRL+ALT+V", stop_listener=lambda: None,
                              _start_listener=lambda: None)
    ui = ns["CardVoiceUI"](queue.Queue(), lambda: None, hotkeys, app)
    app.set_theme = lambda value: ui.apply_theme(value)
    try:
        ui.start()
        ui._open_settings_dialog()
        ui.root.update()
        switch = next(widget for widget, _, _ in ui._theme_bindings[ui.settings_dialog]
                      if isinstance(widget, ns["ToggleSwitch"]))
        switch._invoke()
        assert app.copy_to_clipboard
        for theme in ("light", "dark"):
            ui.apply_theme(theme)
            ui.root.update()
            assert switch.variable.get()
            assert switch._palette is ns["THEME_PALETTES"][theme]
            assert switch.cget("bg") == ns["THEME_PALETTES"][theme]["bg"]
        assert ns["load_config"]() == {"copy_to_clipboard": True, "theme": "dark"}
        ui.settings_dialog.destroy()
        ui._open_settings_dialog()
        ui.root.update()
        reopened = next(widget for widget, _, _ in ui._theme_bindings[ui.settings_dialog]
                        if isinstance(widget, ns["ToggleSwitch"]))
        assert reopened.variable.get()
        assert not any(isinstance(widget, tk.Checkbutton) for widget, _, _ in ui._theme_bindings[ui.settings_dialog])
    finally:
        if ui.root is not None:
            ui.root.destroy()


def test_microphone_circle_uses_antialiased_image(tk_window):
    ns = load_ui_namespace()
    app = SimpleNamespace(theme="dark", copy_to_clipboard=False)
    ui = ns["CardVoiceUI"](queue.Queue(), lambda: None,
                           SimpleNamespace(get_display_text=lambda: "CTRL+ALT+V"), app)
    try:
        ui.start()
        for active in (False, True):
            ui._draw_mic_button(active=active)
            assert ui._mic_active is active
            kinds = [ui.mic_btn_canvas.type(item) for item in ui.mic_btn_canvas.find_all()]
            assert kinds.count("image") == 1
            assert "oval" not in kinds
    finally:
        if ui.root is not None:
            ui.root.destroy()
