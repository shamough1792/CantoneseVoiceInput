"""驗證視窗外框交由合成器圓角，避免透明色鍵與區域裁切互相干擾。"""
import ast
import ctypes
from pathlib import Path
from types import SimpleNamespace

from test_theme_behavior import load_ui_namespace


class NativeCall:
    def __init__(self, result=1):
        self.result = result
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


def corner_environment(native_result=0, region_result=1):
    namespace = load_ui_namespace()
    user32 = SimpleNamespace(GetAncestor=NativeCall(202), SetWindowRgn=NativeCall(region_result))
    gdi32 = SimpleNamespace(CreateRoundRectRgn=NativeCall(303), DeleteObject=NativeCall())
    dwmapi = SimpleNamespace(DwmSetWindowAttribute=NativeCall(native_result))
    namespace["ctypes"] = SimpleNamespace(
        windll=SimpleNamespace(user32=user32, gdi32=gdi32, dwmapi=dwmapi),
        c_void_p=ctypes.c_void_p, c_uint=ctypes.c_uint, c_int=ctypes.c_int,
        c_long=ctypes.c_long, byref=ctypes.byref, sizeof=ctypes.sizeof,
    )
    window = SimpleNamespace(update_idletasks=lambda: None, winfo_id=lambda: 101,
                             winfo_width=lambda: 360, winfo_height=lambda: 540)
    return namespace, window, user32, gdi32, dwmapi


def test_native_corners_target_actual_toplevel_and_avoid_region_clipping():
    ns, window, user32, gdi32, dwmapi = corner_environment()
    assert ns["_apply_rounded_window"](window) is True
    assert user32.GetAncestor.calls == [(101, 2)]
    corner_call = next(call for call in dwmapi.DwmSetWindowAttribute.calls if call[1] == 33)
    assert corner_call[0] == 202
    assert ctypes.cast(corner_call[2], ctypes.POINTER(ctypes.c_int)).contents.value == 2
    assert not gdi32.CreateRoundRectRgn.calls
    assert all(call[1] is None for call in user32.SetWindowRgn.calls)


def test_unsupported_compositor_falls_back_without_leaking_failed_region():
    ns, window, user32, gdi32, _ = corner_environment(native_result=-1, region_result=0)
    assert ns["_apply_rounded_window"](window) is False
    assert gdi32.CreateRoundRectRgn.calls == [(0, 0, 361, 541, 36, 36)]
    assert user32.SetWindowRgn.calls[-1] == (202, 303, True)
    assert gdi32.DeleteObject.calls == [(303,)]


def test_toolbar_does_not_cut_corners_with_transparent_color_or_polygon():
    source = (Path(__file__).resolve().parents[1] / "main.pyw").read_text(encoding="utf-8")
    tree = ast.parse(source)
    ui_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CardVoiceUI")
    start = next(node for node in ui_class.body if isinstance(node, ast.FunctionDef) and node.name == "start")
    start_source = ast.get_source_segment(source, start)
    assert "-transparentcolor" not in start_source
    assert "_draw_round_rect(" not in start_source
    assert "_apply_rounded_window(self.root" in start_source
    assert 'self.root.attributes("-alpha", 0.82)' in start_source
