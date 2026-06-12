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
- **How:** USB devices, monitors, input devices, battery, audio — per-OS
  enumeration following the F2 pattern, **each its own sibling collector**
  (ADR-012), not one grouped section.
- **DoD:** ✅ five real peripheral sections, each returning real data per OS (or
  an honest gap), verified live on Windows + WSL2 smoke. 143 tests green.
  - **`usb`** (ADR-011): `Win32_PnPEntity` / `lsusb`→sysfs / `SPUSBDataType`,
    flat list keyed by VID:PID. (Renamed from the F3-initial `peripherals`.)
  - **`monitors`**: `WmiMonitorID` / raw EDID parse of `/sys/class/drm/*/edid`
    / `SPDisplaysDataType` — manufacturer PnP-ID, product code, serial, name.
  - **`battery`**: `Win32_Battery` / `/sys/class/power_supply/BAT*` (+ health %)
    / `SPPowerDataType` — degrades to an accurate `no battery present`.
  - **`input`**: `Win32_Keyboard`+`Win32_PointingDevice` / `/proc/bus/input/
    devices` / macOS `unsupported`.
  - **`audio`**: `Win32_SoundDevice` / `/proc/asound/cards` / `SPAudioDataType`.
- **Extras ✅ (2026-06-11):** two more sibling collectors on the same pattern —
  **`bluetooth`** (`Win32_PnPEntity` BT class · `bluetoothctl`+`/sys/class/
  bluetooth` · `SPBluetoothDataType`; adapters *and* paired devices as separate
  levels, ADR-014) and **`printers`** (`Win32_Printer` · `lpstat -p`/`-d` CUPS ·
  `SPPrintersDataType`). 19 offline tests (204 total green). Verified live on
  Windows (no BT radio → clean `unavailable`; 9 print queues, default flagged)
  and WSL2 (no BT stack / no CUPS → clean `unavailable`, zero ERROR). See ADR-014.

## F2.x — Physical storage drives  ✅ (2026-06-11)

- **Objective:** close the deep-hardware gap `disk` leaves — `disk` reports
  psutil partitions/usage only, not the physical drives.
- **How:** a `storage_devices` collector for drive **model / serial / firmware /
  bus type (SSD/HDD/NVMe) / SMART health** — `MSFT_PhysicalDisk`
  (+ `Win32_DiskDrive` fallback, `MSStorageDriver_FailurePredictStatus` SMART) on
  Windows, `lsblk -d -b -O -J`/`/sys/block` (Linux, `smartctl` for SMART),
  `diskutil info -all` (macOS), per ADR-013 (same judgement as ADR-009/010).
- **DoD:** ✅ a `storage_devices` sibling section (ADR-012), separate from the
  untouched psutil `disk`. Per drive: model / serial / firmware / size / bus /
  media + health where readable; degrades to UNAVAILABLE/PARTIAL with an
  elevation note, never raises. **42 offline tests** (canned `lsblk -J`, tmp
  `/sys/block` tree, stubbed CIM/`run_command`); 185 total green. Verified live
  on Windows (ADATA SATA SSD + SanDisk USB — bus/media/health unprivileged) and
  WSL2 (4 Hyper-V virtual disks via lsblk → PARTIAL + smartctl/root note, exit 0).
  See ADR-013.

## F4 — Richer HTML report + scan diff  ✅ (2026-06-11)

- **Objective:** a genuinely shareable artifact.
- **How:** collapsible sections, search/filter, copy-as-JSON; a **diff**
  between two saved scans ("what changed on this machine").
- **DoD:** ✅ both deliverables landed, single self-contained HTML, no external
  assets, diff works on two sample scans.
  - **Interactive HTML** (ADR-015): native `<details>` collapse (degrades to a
    readable static page with JS off), a search box filtering by section
    name / key / value, copy-as-JSON per section *and* whole-scan, and nested
    data rendered as a recursive HTML tree (ADR-007's twin), not a `<pre>` dump.
    Single self-contained file — inline CSS + inline vanilla JS, zero external
    `src`/`href`/CDN. Verified live on Windows (16-section scan → 0 external
    refs, 16 collapsible cards, 0 `<pre>`) and WSL2.
  - **Scan diff** (`report/diff.py`): a pure, renderer-agnostic `diff_scans`
    over two saved `Inventory.to_dict()` JSON scans → sections added / removed
    and per-section field-level changes on a deterministic index-based path
    (`data.devices[2].vid`). Text + self-contained-HTML + JSON renderers.
    CLI: `--diff OLD.json NEW.json` (text default; `--html` / `--json` change
    the form; `-o` to write a file). Loads saved scans, never re-scans.
  - **20 offline tests** (`test_html_report.py`, `test_diff.py`, +3 CLI diff
    tests): self-containment, search/collapse/copy scaffolding, nested tree,
    and diff add/remove/change incl. the no-change (empty) case. 224 total green.

## F5 — Packaged binaries (USB-stick deliverable)  ✅ (2026-06-12)

- **Objective:** the "plug into anything" story, realistically.
- **How:** PyInstaller one-file specs in `build/` per OS; a release workflow
  producing `machine-scanner-{win,linux,macos}`; a short stick layout doc.
- **Double-click default (binary UX):** when the **frozen** binary is run with
  **no arguments** (i.e. double-clicked), it must not just flash a console — it
  writes an HTML report to a file and opens it. Default name
  **`machine_inventory.html`**, gated on `sys.frozen` + no-args so the normal
  CLI default (text to stdout) is unchanged; also expose it as an explicit
  `--report` flag for terminal users. Write next to the binary (cwd), open via
  `webbrowser`.
- **Localized filename (best-effort, pure stdlib):** the default report filename
  is translated by a **small hardcoded language→name map** keyed on the detected
  OS UI language (`locale` / Windows `GetUserDefaultUILanguage` / `$LANG`), English
  as fallback: `en → machine_inventory`, `pt → inventario_de_maquina` (+ a few:
  es/fr/de). So a PT-BR box yields `inventario_de_maquina.html`. **Filename only**
  — report *content* stays English (the "English everywhere" rule + full i18n is
  out of scope; parked under Ideas). No new deps, offline.
- **DoD:** ✅ a downloadable binary per OS that runs with no Python installed; a
  double-click on the binary produces (and opens) a localized-name HTML report.
  - **One-file spec** (`build/machine_scanner.spec` + `entrypoint.py`, ADR-018):
    one spec → one binary per OS, self-named from the build OS; `pyinstaller` a
    build-time-only `[build]` extra (ADR-001 intact). Built + verified live on
    Windows: `dist/machine-scanner-windows.exe` (7.4 MB), clean-shell `--list`
    → all 16 collectors, `--json`/`--html`/`--diff`/`--report` exit 0, 0 external
    refs in the HTML.
  - **Frozen double-click UX** (ADR-017): `sys.frozen`+no-args → write+open an
    HTML report (CLI text default untouched); `--report` for terminals; default
    filename localized by OS language (`inventario_de_maquina.html` confirmed
    live on a pt-BR box), content stays English. +12 offline tests (239 total).
  - **Release workflow** (`release.yml`): tag-triggered `v*`, builds on
    windows/ubuntu/macos-latest with a per-OS `--list`==16 smoke gate, uploads
    three artifacts to a GitHub Release. Linux/macOS binaries are produced there
    (not buildable on the Windows dev box / WSL-no-pip). Stick-layout doc in
    `build/README.md`. **Remaining:** push a `v0.1.0` tag to mint the cross-OS
    binaries (polish, not a phase).

## Ideas parked (not scheduled)

- Scan **diff/history** as a first-class feature (overlaps F4).
- Export presets (CSV of partitions, a one-line summary for ticket systems).
- A `--watch` mode for live metrics — likely out of scope (this is an inventory
  tool, not a monitor).
- **Full report-content i18n** (translating section labels / values, not just the
  filename) — deferred: it conflicts with the "English everywhere" rule and is a
  real i18n effort. F5 only localizes the default *filename*.
