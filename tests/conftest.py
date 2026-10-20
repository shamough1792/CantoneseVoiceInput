"""UI 測試共用單一 Tk 直譯器，各測試仍使用獨立的真正視窗。"""
import tkinter as tk

import pytest


@pytest.fixture(scope="session")
def tk_runtime():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def tk_window(tk_runtime, monkeypatch):
    windows = []

    def create():
        window = tk.Toplevel(tk_runtime)
        window.mainloop = lambda: None
        windows.append(window)
        return window

    monkeypatch.setattr(tk, "Tk", create)
    yield create
    for window in windows:
        if window.winfo_exists():
            window.destroy()
