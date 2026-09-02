# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

repo_root = Path(SPEC).resolve().parent.parent
web_root = repo_root / "vibegap" / "ui" / "web"
dicts_root = repo_root / "dicts"
app_a = Analysis(
    [str(repo_root / "packaging" / "entry.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=[(str(web_root), "vibegap/ui/web"), (str(dicts_root), "dicts")],
    hiddenimports=["webview.platforms.edgechromium", "webview.platforms.winforms"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "cefpython3",
        "gi",
        "kivy",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "tkinter",
    ],
    noarchive=False,
    optimize=0,
)
hook_a = Analysis(
    [str(repo_root / "packaging" / "hook_entry.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
app_pyz = PYZ(app_a.pure)
hook_pyz = PYZ(hook_a.pure)

app_exe = EXE(
    app_pyz,
    app_a.scripts,
    [],
    exclude_binaries=True,
    name='VibeGap',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='_internal',
)
hook_exe = EXE(
    hook_pyz,
    hook_a.scripts,
    [],
    exclude_binaries=True,
    name="VibeGapHook",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
    hide_console="hide-early",
)
coll = COLLECT(
    app_exe,
    hook_exe,
    app_a.binaries,
    app_a.datas,
    hook_a.binaries,
    hook_a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VibeGap',
)
