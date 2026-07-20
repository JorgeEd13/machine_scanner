# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file spec — the requirements checker (ROADMAP F6.1).

A second, smaller binary from the same codebase:

    ai-model-requirements-windows.exe   (built on windows-latest)
    ai-model-requirements-linux         (built on ubuntu-latest)
    ai-model-requirements-macos         (built on macos-latest)

Build (from the repo root, with the build extra installed):

    pyinstaller build/ai_model_requirements.spec

**Why a separate binary rather than a flag on the scanner.** This one is handed
to someone who did not go looking for it and has no reason to trust it yet. Two
consequences that a flag could not deliver:

* **It bundles only the collectors it uses.** The five in ``qualifier.SCOPE``,
  not all seventeen — so the claim "it does not read your network interfaces or
  your serial numbers" is true of the *artifact*, not merely of its default
  behaviour. There is no argument that turns this build into a full inventory.
* **Double-click is the whole interaction.** No flags to discover.

Icon: the shared brand mark, same as the scanner (Windows .ico).
"""

import os
import sys

_SRC = os.path.join(SPECPATH, os.pardir, "src")
_ENTRY = os.path.join(SPECPATH, "entrypoint_qualifier.py")

if sys.platform.startswith("win"):
    _NAME = "ai-model-requirements-windows"
elif sys.platform == "darwin":
    _NAME = "ai-model-requirements-macos"
else:
    _NAME = "ai-model-requirements-linux"

_ICON = os.path.join(SPECPATH, "machine_scanner.ico")
_icon = _ICON if os.path.exists(_ICON) else None


a = Analysis(
    [_ENTRY],
    pathex=[_SRC],
    binaries=[],
    datas=[],
    # Only the scoped collectors. Keep this list identical to
    # `machine_scanner.qualifier.SCOPE` — a test asserts they match, because a
    # drift here would either break the check or quietly widen what it reads.
    hiddenimports=[
        "machine_scanner.collectors.cpu",
        "machine_scanner.collectors.memory",
        "machine_scanner.collectors.gpu",
        "machine_scanner.collectors.disk",
        "machine_scanner.collectors.llm_runtime",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The collectors this build must NOT contain. Excluding them is what makes
    # the privacy claim a property of the binary instead of a promise about how
    # it is invoked.
    excludes=[
        "machine_scanner.collectors._all",  # the manifest — pulls in everything
        "machine_scanner.collectors.system",
        "machine_scanner.collectors.network",
        "machine_scanner.collectors.usb",
        "machine_scanner.collectors.monitors",
        "machine_scanner.collectors.storage_devices",
        "machine_scanner.collectors.baseboard",
        "machine_scanner.collectors.memory_modules",
        "machine_scanner.collectors.bluetooth",
        "machine_scanner.collectors.printers",
        "machine_scanner.collectors.battery",
        "machine_scanner.collectors.input_devices",
        "machine_scanner.collectors.audio",
    ],
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
