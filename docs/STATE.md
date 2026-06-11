# STATE — machine_scanner

> Volatile, short. Update at the end of each step.

**Date:** 2026-06-11
**Phase:** F3 (peripherals) — ✅ **closed** for **5 categories** (usb, monitors,
battery, input, audio), each its own sibling section (ADR-012). Next: **F4**
(richer HTML + scan diff), or the queued F3 extras (Bluetooth, printers).

## Current focus

F3 split into **per-category sibling collectors** (ADR-012) — not one grouped
`peripherals` section. The original `peripherals` (USB) was **renamed to `usb`**
(data key `usb`→`devices`). Five peripheral sections now ship, each with its own
honest status and per-collector isolation:

- **`usb`** (ADR-011): flat `{name, vendor_id, product_id, manufacturer}` keyed
  by **VID:PID**. Windows `Win32_PnPEntity` (CIM), Linux `lsusb`→`/sys/bus/usb`
  fallback, macOS `SPUSBDataType`.
- **`monitors`**: Windows `WmiMonitorID` (root\wmi, char-code arrays decoded),
  **Linux raw EDID parse** of `/sys/class/drm/*/edid` (`_parse_edid` — manufacturer
  PnP-ID, product code, serial, monitor name), macOS `SPDisplaysDataType`.
- **`battery`**: Windows `Win32_Battery` (`@()`+`-InputObject` so a battery-less
  box emits `[]`, telling "no battery" apart from a query failure), Linux
  `/sys/class/power_supply/BAT*` (+ design-vs-full health %), macOS
  `SPPowerDataType`.
- **`input`**: Windows `Win32_Keyboard`+`Win32_PointingDevice`, Linux
  `/proc/bus/input/devices` (classify by `Handlers=`), macOS → `unsupported`
  (inputs surface under `usb` there).
- **`audio`**: Windows `Win32_SoundDevice`, Linux `/proc/asound/cards`, macOS
  `SPAudioDataType`.

**143 tests green** locally (was 108). All degrade to `unavailable`/`unsupported`
without raising.

## Done (F3)

- 5 collector modules + `tests/test_{usb,monitors,battery,input_devices,audio}.py`
  (offline: monkeypatch `run_cim`/`run_command`, tmp sysfs/proc dirs, a hand-built
  EDID blob). `peripherals.py`/`test_peripherals.py` removed in the rename.
- ADR-012 (split into siblings + the `peripherals`→`usb` rename; supersedes the
  "add a key" note in ADR-011).
- **Verified live on Windows**: usb (Logitech/SanDisk/Intel), **monitors (2×
  Samsung — SAM PnP-ID + product code + serial via WmiMonitorID)**, input
  (keyboard+pointer), audio (HD Audio), **battery → clean `no battery present`**.
  **WSL2 smoke**: all five → clean `[n/a]`, zero ERROR sections.

## Prior phase (F2) — reference

F2 closed: three probes reach *past* psutil into firmware — `baseboard`
(board / BIOS / serials), `gpu` (multi-vendor: AMD/Intel/iGPU + NVIDIA), and
`memory_modules` (per-DIMM). All per-OS via `run_command`/sysfs, all degrade to
`unsupported`/`unavailable` without raising. Was 88 tests green.

## Prior phase (F1) — reference

F1 closed earlier: recursive text renderer (ADR-007), no-psutil path, exit
codes (ADR-008), GitHub Actions matrix {ubuntu, windows} × {3.9, 3.13}, WSL
smoke run. Was 24 tests; CI observed green (run 27347587254).

## Next step

Open directions (pick per session):
- **F3 extras (queued)** — two more peripheral siblings on the same pattern:
  **Bluetooth** (`Win32_PnPEntity` BT class · `bluetoothctl`/`/sys/class/bluetooth`
  · `SPBluetoothDataType`) and **printers** (`Win32_Printer` · `lpstat -p` ·
  `SPPrintersDataType`).
- **F2.x — physical storage drives** (recorded in ROADMAP): a `storage_devices`
  collector for drive **model / serial / firmware / bus (SSD/HDD/NVMe) / SMART**
  — the real gap left by `disk` (psutil partitions only). `Win32_DiskDrive` ·
  `lsblk`+`/sys/block` · `diskutil`.
- **F4 — richer HTML report + scan diff** (the next numbered phase).

## Notes / open points

- CI should stay green (no new deps; all new tests are offline). Prior runs green.
- Live Windows shows real data for all 5 peripheral sections; **battery degrades
  to an accurate `no battery present`** on this desktop (the `@()`+`-InputObject`
  trick distinguishes "no rows" from "query failed" — see `_PS_BAT`).
- WSL2 exposes no `lsusb` / DRM EDID / `BAT*` / `/proc/asound` → all 5 peripheral
  sections are `[n/a]` there (verified, zero ERROR); parse paths are covered by
  offline tmp-dir / canned-output / hand-built-EDID tests instead.
- WSL has no `pip`, so pytest wasn't run there; CI's ubuntu job covers
  pytest-on-Linux. The WSL CLI run was enough to confirm cross-OS execution.
- Known cosmetic: non-ASCII device names (PT-BR locale) show console-codepage
  mojibake in the *text* renderer on Windows; the JSON is correct. Pre-existing,
  not specific to peripherals — candidate cleanup, not a blocker.
