# ROADMAP — machine_scanner

> **Living list:** a new need mid-way becomes a phase/pending item here, not a
> note lost in chat. Each phase has Objective / How / Definition of Done (DoD).
> One step at a time, across sessions, without breaking what works.

## F0 — Foundations & runnable skeleton  ✅ (2026-06-11)

- **Objective:** a clean, runnable scaffold that proves the architecture.
- **How:** src-layout package; core (models/platform/registry); 7 collectors
  (5 real, 1 NVIDIA GPU, 1 stub); json/text/html renderers; argparse CLI;
  offline pytest; docs + license.
- **DoD:** ✅ `python -m machine_scanner` produces text/JSON/HTML; `--only` and
  `--list` work; `pytest` green (10). Verified on Windows.

## F1 — Hardening & ergonomics  ✅ (2026-06-11)

- **Objective:** make it robust and CI-backed across OSes.
- **How:** nested-list text rendering (interface addresses / partitions as
  tables); no-psutil code path test; clearer exit codes; **GitHub Actions**
  (`pytest` on ubuntu + windows); Linux/WSL smoke run.
- **DoD:** ✅ recursive text renderer (ADR-007) — nested data reads as an
  outline, verified on a live Windows scan; no-psutil path tested
  (`tests/test_no_psutil.py`); exit codes 0/2 (ADR-008) with CLI tests; GitHub
  Actions matrix ubuntu+windows × py3.9/3.13 running pytest + a CLI smoke run;
  Linux smoke run done under WSL (Ubuntu, py3.12 — also exercised the no-psutil
  fallback for real). 24 tests green. CI will confirm green on the GitHub
  runners on first push.

## F2 — Deeper hardware (per-OS)  ✅ (2026-06-11)

- **Objective:** go beyond what psutil exposes.
- **How:** GPU for AMD/Intel/integrated; motherboard / BIOS / RAM slots /
  serials via WMI (Windows), `dmidecode`/`lshw` (Linux), `system_profiler`
  (macOS) — all through `core.platform.run_command`. Surface privilege caveats.
- **DoD:** ✅ three deep collectors, each working on its OS and degrading to a
  graceful `unsupported`/`unavailable`/`partial` elsewhere with elevation notes:
  - `baseboard` — board / BIOS / serials (ADR-009): Windows CIM, Linux sysfs
    DMI, macOS `system_profiler`.
  - `gpu` — now **multi-vendor** (ADR-010): Windows `Win32_VideoController`,
    Linux `lspci`→sysfs PCI-ID fallback, macOS `SPDisplaysDataType`, + NVIDIA
    enriched via `nvidia-smi`.
  - `memory_modules` — per-DIMM (ADR-010): Windows `Win32_PhysicalMemory`, Linux
    `dmidecode -t memory` (root-gated), macOS `SPMemoryDataType`.
  Shared `_smbios.py` helper (CIM→JSON + placeholder scrub). 88 tests green;
  verified live on Windows + WSL2 smoke.

## F3 — Peripherals & extras  ✅ (2026-06-11)

- **Objective:** flesh out the registered `peripherals` stub.
- **How:** USB devices, monitors, input devices, battery/sensors — per-OS
  enumeration following the F2 pattern.
- **DoD:** ✅ `peripherals` returns real data on each OS (or honest gap). The
  stub is now a real **USB devices** collector (ADR-011): Windows
  `Win32_PnPEntity` (CIM), Linux `lsusb` → `/sys/bus/usb` fallback, macOS
  `SPUSBDataType`; normalized to a flat `{name, vendor_id, product_id,
  manufacturer}` list keyed by VID:PID; no elevation needed; degrades to a clean
  `unavailable` (verified live on Windows + WSL2 smoke). 108 tests green.
- **Follow-ups (same dispatch shape, optional):** monitors (`WmiMonitorID`/EDID
  · `/sys/class/drm/*/edid` · `SPDisplaysDataType`), battery (`Win32_Battery` ·
  `/sys/class/power_supply` · `pmset`), input devices. New categories add a key
  to the `peripherals` section rather than a new collector.

## F4 — Richer HTML report

- **Objective:** a genuinely shareable artifact.
- **How:** collapsible sections, search/filter, copy-as-JSON; optional **diff**
  between two saved scans ("what changed on this machine").
- **DoD:** single self-contained HTML, no external assets, diff works on two
  sample scans.

## F5 — Packaged binaries (USB-stick deliverable)

- **Objective:** the "plug into anything" story, realistically.
- **How:** PyInstaller one-file specs in `build/` per OS; a release workflow
  producing `machine-scanner-{win,linux,macos}`; a short stick layout doc.
- **DoD:** a downloadable binary per OS that runs with no Python installed.

## Ideas parked (not scheduled)

- Scan **diff/history** as a first-class feature (overlaps F4).
- Export presets (CSV of partitions, a one-line summary for ticket systems).
- A `--watch` mode for live metrics — likely out of scope (this is an inventory
  tool, not a monitor).
