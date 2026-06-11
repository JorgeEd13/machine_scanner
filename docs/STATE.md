# STATE — machine_scanner

> Volatile, short. Update at the end of each step.

**Date:** 2026-06-11
**Phase:** F3 (peripherals) — ✅ **closed** for the **USB** category. The
`peripherals` stub is now a real per-OS collector. Next: **F4** (richer HTML +
scan diff), or the optional F3 follow-up categories (monitors / battery / input).

## Current focus

F3 first category shipped: `peripherals` enumerates **USB devices** per-OS and
normalizes them to a flat `{name, vendor_id, product_id, manufacturer}` list
keyed by **VID:PID** (ADR-011). Windows `Win32_PnPEntity` (CIM), Linux `lsusb` →
`/sys/bus/usb` fallback, macOS `SPUSBDataType`; no elevation needed; degrades to
clean `unavailable`. **108 tests green** locally (was 88).

## Done (F3 — USB)

- **`collectors/peripherals.py`** (ADR-011): replaced the `unsupported` stub.
  Per-OS dispatch mirroring the F2 collectors; reuses `_smbios.run_cim` on
  Windows. Flat list (not the USB tree), hubs kept (honest over-inclusion), VID:
  PID as the cross-OS identity. macOS controller/bus *headers* drop out
  naturally (no VID/PID).
- **`tests/test_peripherals.py`** (20): VID/PID extraction, hex-id normalization,
  Windows CIM parse + placeholder scrub + command-failure → UNAVAILABLE, Linux
  `lsusb` parse, **sysfs fallback via a tmp dir**, interface-node skip (driven
  through `listdir` since NTFS forbids `:` in names), macOS tree parse,
  unsupported OS, never-raises.
- **Verified live on Windows** (Logitech 046d receiver, SanDisk 0781:5567 mass
  storage, Intel 8087 hubs — all with VID:PID) and via **WSL2 smoke** (no
  `lsusb`, no `/sys/bus/usb` → clean `UNAVAILABLE` + accurate note, no crash).

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

Two open directions (pick per session):
- **F4 — richer HTML report + scan diff** (the next planned phase).
- **F3 follow-up categories** (optional, same dispatch shape, each adds a key to
  the `peripherals` section, not a new collector): **monitors** (`WmiMonitorID`/
  EDID · `/sys/class/drm/*/edid` · `SPDisplaysDataType`), **battery**
  (`Win32_Battery` · `/sys/class/power_supply` · `pmset` — note: this desktop
  has no battery, so design it to degrade to `unavailable` cleanly), **input
  devices**.

## Notes / open points

- CI should stay green (no new deps; all new tests are offline). Prior runs green.
- `peripherals` (USB) now lists real devices on this box; on WSL2 it degrades to
  `unavailable` (no `lsusb`, no `/sys/bus/usb`), like the F2 deep collectors.
- WSL2 exposes no DMI / `lspci` / `dmidecode` / `lsusb` → the deep collectors and
  peripherals are `unavailable` there (verified); their parse paths are covered
  by offline tmp-dir / canned-output tests instead.
- WSL has no `pip`, so pytest wasn't run there; CI's ubuntu job covers
  pytest-on-Linux. The WSL CLI run was enough to confirm cross-OS execution.
