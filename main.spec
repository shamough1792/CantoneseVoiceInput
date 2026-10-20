# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.pyw'],
    pathex=[],
    binaries=[],
    datas=[
        ('res/snd_start.wav', 'res'),
        ('res/snd_success.wav', 'res'),
        ('res/snd_fail.wav', 'res'),
    ],
    hiddenimports=['selenium.webdriver.chrome.webdriver'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CantoneseVoiceInput',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX 壓縮會提高部分防毒軟體的啟發式誤報率；發佈版停用。
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app.ico'],
)
