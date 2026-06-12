# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file spec — one binary per OS from one codebase (ROADMAP F5).

There is no single binary that runs on every OS (PLAN's "reality check"), so the
deliverable is one executable per OS built from this same spec:

    machine-scanner-windows.exe   (built on windows-latest)
    machine-scanner-linux         (built on ubuntu-latest)
    machine-scanner-macos         (built on macos-latest)

Build (from the repo root, with the dev/build extra installed):

    pyinstaller build/machine_scanner.spec

Output lands in dist/ (git-ignored). The OS-specific name is chosen here from
sys.platform so the same spec yields the right artifact name on each runner.

One-file (ADR-018): a single self-contained executable that unpacks to a temp
dir at startup — true to the "drop one file on a stick" promise (ADR-015's
zero-external-asset HTML report continues that promise at the report layer), at
the cost of a small first-run extraction delay. Icon: if build/machine_scanner.ico
exists it is embedded (Windows); otherwise the default PyInstaller icon is used,
so a future brand icon needs no spec change.
"""

import os
import sys

# SPECPATH is injected by PyInstaller as the directory holding this spec (build/).
_SRC = os.path.join(SPECPATH, os.pardir, "src")
_ENTRY = os.path.join(SPECPATH, "entrypoint.py")

if sys.platform.startswith("win"):
    _NAME = "machine-scanner-windows"
elif sys.platform == "darwin":
    _NAME = "machine-scanner-macos"
else:
    _NAME = "machine-scanner-linux"

# Optional brand icon (Windows .ico). Auto-used when present; see
# reference_brand_logo — a refined high-contrast variant is the trigger.
_ICON = os.path.join(SPECPATH, "machine_scanner.ico")
_icon = _ICON if os.path.exists(_ICON) else None


a = Analysis(
    [_ENTRY],
    pathex=[_SRC],
    binaries=[],
    datas=[],
    # The collectors self-register via explicit imports in
    # collectors/__init__ (ADR-002), so PyInstaller's import-graph analysis
    # already pulls them in. Listing them here too is belt-and-suspenders: it
    # guarantees the frozen --list shows all 16 even if analysis ever changes.
    hiddenimports=[
        "machine_scanner.collectors.system",
        "machine_scanner.collectors.cpu",
        "machine_scanner.collectors.memory",
        "machine_scanner.collectors.disk",
        "machine_scanner.collectors.network",
        "machine_scanner.collectors.gpu",
        "machine_scanner.collectors.baseboard",
        "machine_scanner.collectors.memory_modules",
        "machine_scanner.collectors.storage_devices",
        "machine_scanner.collectors.usb",
        "machine_scanner.collectors.monitors",
        "machine_scanner.collectors.audio",
        "machine_scanner.collectors.input_devices",
        "machine_scanner.collectors.battery",
        "machine_scanner.collectors.bluetooth",
        "machine_scanner.collectors.printers",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)
