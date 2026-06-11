# STATE — machine_scanner

> Volatile, short. Update at the end of each step.

**Date:** 2026-06-11
**Phase:** F3-extras (`bluetooth` + `printers`) — ✅ **closed**. Two more
peripheral sibling collectors (ADR-014 for the non-obvious Bluetooth choice),
shipped together like the F3 five. With this the F3 bucket is fully done. Next:
**F4** (richer HTML + scan diff) — the next numbered phase.

## Current focus (F3-extras)

Two new sibling sections on the established ADR-012 pattern (own module + section
+ test file each, registered in `collectors/__init__.py`):

- **`bluetooth`** (ADR-014) — reports the radio and the paired peers as **two
  separate levels**: data is `{"adapters": [...], "devices": [...]}` (+ counts);
  a radio with no paired devices is still `ok`, only *neither* → `unavailable`.
  - **Windows** `Win32_PnPEntity` where `PNPClass='Bluetooth'` (CIM, `@()`-wrapped
    to tell "no BT" from a query failure); rows split by `PNPDeviceID` —
    `DEV_<mac>` → paired device, `BTHENUM\{guid}_…` service node dropped, else the
    adapter.
  - **Linux** `bluetoothctl devices` (device level — it resolves remote *names*
    sysfs can't) **complemented** by `/sys/class/bluetooth/hci*` (adapter level);
    no daemon / no `hciX` → clean `unavailable`.
  - **macOS** `SPBluetoothDataType` (nested controller + Connected/Not Connected).
- **`printers`** (no ADR — straightforward ADR-011 shape): **Windows**
  `Win32_Printer` (name/default/port/driver/shared/network/offline, `@()`-wrapped);
  **Linux** `lpstat -p` + `-d` (CUPS; no `lpstat`/no cupsd → clean `unavailable`);
  **macOS** `SPPrintersDataType`.

**204 tests green** (was 185; +19). Never raise; UNAVAILABLE/UNSUPPORTED with
accurate notes.

### Verified
- **Windows live**: `bluetooth` → clean **`unavailable`** ("no Bluetooth-class
  devices", this desktop has no radio — correctly *not* an ERROR); `printers` →
  **`ok`** with 9 real queues (HP DesignJet network printer flagged `default`,
  Brother + virtual MS/OneNote/AnyDesk queues), all unprivileged.
- **WSL2 smoke**: both → clean **`unavailable`** (no `/sys/class/bluetooth` + no
  `bluetoothctl`; no CUPS/`lpstat`), zero ERROR.

## Prior phase (F2.x) — reference

`storage_devices` — the deep-hardware layer `disk` was missing (`disk` stays the
psutil partitions/usage view, untouched). Its own sibling `Section` (ADR-012);
per drive: model / serial / firmware / size_gb / **bus** (NVMe/SATA/USB) /
**media** (SSD/HDD) / **health**. Per-OS source per ADR-013:

- **Windows** — `MSFT_PhysicalDisk` (`root\microsoft\windows\storage`) is the
  spine: clean MediaType + BusType enums **and** a no-admin storage-stack
  `HealthStatus`. `Win32_DiskDrive` is the older-Windows fallback (no media,
  coarse bus). SMART predictive-failure (`MSStorageDriver_FailurePredictStatus`,
  `root\wmi`) is best-effort and admin-gated → PARTIAL + elevation note when
  blocked; not correlated per-drive (InstanceName carries no disk number), so
  reduced to a fleet-wide note.
- **Linux** — `lsblk -d -b -O -J` (parse JSON: model/serial/`rev`/size/`rota`/
  `tran`); `/sys/block/*` fallback when lsblk absent (bus-poor, noted). SMART via
  `smartctl -H -j` needs root → PARTIAL + note when unreadable.
- **macOS** — `diskutil info -all`, keeping only `Virtual: No` blocks.

**185 tests green** (was 143; +42 for storage). Registered in
`collectors/__init__.py`. Never raises; UNAVAILABLE/PARTIAL with accurate notes.

### Verified
- **Windows live**: ADATA SU650 (SATA/SSD) + SanDisk Cruzer Blade (USB) — full
  model/serial/firmware/size + `health: healthy`, all **unprivileged**
  (`elevated: false`). The SMART predictive query returned empty (no rows)
  without admin, so it correctly did **not** false-gate to PARTIAL.
- **WSL2 smoke**: lsblk exposes 4 Hyper-V virtual disks → enumerated via the
  lsblk-JSON path; `smartctl` absent → clean **PARTIAL** with the root/smartctl
  note, zero ERROR, exit 0.

## Prior phase (F3) — reference

F3 split into **per-category sibling collectors** (ADR-012) — not one grouped
`peripherals` section. The original `peripherals` (USB) was **renamed to `usb`**
(data key `usb`→`devices`). Five peripheral sections ship, each with its own
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

- **F4 — richer HTML report + scan diff** (the next numbered phase): collapsible
  sections, search/filter, copy-as-JSON, and a diff between two saved scans. This
  is now the head of the queue (F3 and its extras are done).

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
