# STATE — machine_scanner

> Volatile, short. Update at the end of each step.

**Date:** 2026-06-11
**Phase:** F4 (richer interactive HTML + scan diff) — ✅ **closed** (both
deliverables landed in one session). ADR-015 for the interactivity choice.
Next: **F5** (packaged PyInstaller binaries per OS) — the last numbered phase
and now the head of the queue.

## Current focus (F4) — done

Two deliverables, both shipped:

1. **Interactive HTML** (`report/html_report.py`, ADR-015). The static
   one-card-per-section renderer became *interactive* without leaving its single
   self-contained file:
   - **Native `<details>` collapse** — JS-off still gives a readable, collapsible
     static page (progressive enhancement, not a hard dependency).
   - **Search box** filters cards by a precomputed lowercase `data-search`
     haystack (section name + every key/value + notes).
   - **Copy-as-JSON** per section *and* whole-scan, from `data-copy-json`
     attributes via `navigator.clipboard` (+ `<textarea>`/`execCommand` fallback).
   - **Nested data as a recursive HTML tree** (`_render_value`/`_render_mapping`,
     the twin of the text renderer's ADR-007) — `<pre>` only as a leaf fallback,
     never a whole-structure dump.
   - **Inline CSS + inline vanilla JS, zero external assets** (no framework, no
     CDN, no `src`/`href`). Expand-all / collapse-all controls too.
2. **Scan diff** (`report/diff.py`). A **pure, renderer-agnostic** `diff_scans`
   over two saved `Inventory.to_dict()` JSON scans (never a live re-scan):
   `sections_added` / `sections_removed` (each `{name,title,status}`) +
   `sections_changed` (per-section field-level `{path,kind,old,new}` on a
   deterministic index-based path, e.g. `data.devices[2].vid`). An identical
   pair → three empty buckets. Two **pure formatters** beside it — `diff_to_text`
   and a self-contained `diff_to_html` — that display, never compute (ADR-002
   boundary held). CLI: **`--diff OLD.json NEW.json`** (text default; `--html` /
   `--json` change the form; `-o` writes a file).

**224 tests green** (was 204; +20: `test_html_report.py`, `test_diff.py`, +3
CLI diff tests). No new dependency (pure stdlib); never raises. **227** after the
post-F4 encoding fix (ADR-016, `test_platform_encoding.py`).

### Verified
- **Windows live**: `--html` on a real 16-section scan → **0 external
  references** (no `http(s)`/`src=`/`href=`), 16 native-collapsible cards, search
  + copy (17 copy buttons + copy-all) wired, **0 `<pre>` dumps** (nested data is
  a tree). `--diff` on two saved JSON scans (controlled edit) → correct
  `section removed: Audio Devices` + `+ data.fake_metric: 123`; `--html`/`--json`
  diff forms self-contained and exit 0; identical-pair → "no differences".
- **WSL2 smoke**: `--html` → 0 external refs, 16 cards, 0 `<pre>`; two real
  re-scans diffed (`--diff`, text + self-contained HTML) → exit 0, zero ERROR;
  cross-OS parity confirmed.

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

- **F5 — packaged binaries (USB-stick deliverable)** — the last numbered phase,
  now the head of the queue. PyInstaller one-file specs in `build/` per OS + a
  release workflow producing `machine-scanner-{win,linux,macos}` + a short stick
  layout doc. DoD: a downloadable binary per OS that runs with no Python
  installed. (See ROADMAP F5.)
  - **Added requirement (user, 2026-06-11):** double-clicking the **frozen**
    binary with no args must **write + open an HTML report** (not flash a
    console), default name **`machine_inventory.html`**, gated on `sys.frozen` +
    no-args so the CLI text default is untouched (+ a `--report` flag). The
    filename is **localized by a small hardcoded language→name map** keyed on the
    OS UI language (en → `machine_inventory`, pt → `inventario_de_maquina`, +
    es/fr/de), English fallback — **filename only, content stays English**
    (full content i18n is out of scope, parked). Pure stdlib, offline. See
    ROADMAP F5.

## Notes / open points

- CI should stay green (F4 added **no new deps**; all 20 new tests are offline).
  Prior runs green.
- **F4 self-containment contract** (ADR-015): the HTML report and the diff HTML
  are single files with inline CSS + inline vanilla JS and **zero** external
  `http(s)`/`src=`/`href=`. `test_html_report.py` / `test_diff.py` lock this; if
  F5 or later ever adds an asset, those tests must be revisited deliberately.
- The diff keys on a **deterministic index-based path** into nested data — a
  reordered list reads as field changes, not a move. Accepted trade-off for an
  inventory diff (determinism > order-invariance); noted in ADR-015.
- `.gitignore` covers `scan-*.json` / `*.report.html` / `scan-*.html`. Ad-hoc
  verification artifacts named otherwise (e.g. `out.html`, `_wsl_*`) are **not**
  ignored — delete them before committing (done this session).
- WSL has no `pip`, so pytest wasn't run there; CI's ubuntu job covers
  pytest-on-Linux. The WSL CLI run confirms cross-OS execution + self-containment.
- **Fixed 2026-06-11 (ADR-016):** non-ASCII device names (pt-BR) were corrupted
  in the *captured data* (`Aperfeiçoado`→`Aperfei‡oado`), not just the console —
  PowerShell emits OEM cp850, Python was decoding locale cp1252. Fix: force UTF-8
  on both ends (`run_command` decodes UTF-8; every PowerShell call prefixed with
  `POWERSHELL_UTF8`). The earlier "JSON is correct" note was wrong. Verified live
  (`input` → `Aperfeiçoado`, `padrão`; no `‡`/`Æ` in the JSON). +3 tests
  (`test_platform_encoding.py`).
