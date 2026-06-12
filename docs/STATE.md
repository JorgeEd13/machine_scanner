# STATE — machine_scanner

> Volatile, short. Update at the end of each step.

**Date:** 2026-06-12
**Phase:** F5 (packaged PyInstaller binaries per OS — the USB-stick deliverable)
— ✅ **closed**. The **last numbered phase**; all of F0–F5 are now done. ADR-017
(frozen no-args report mode + localized filename) and ADR-018 (one-file /
collector discovery / unsigned) for the choices. Next session = polish/showcase
(README hero image, demo GIF, logo refinement), **not** a numbered phase.

## Current focus (F5) — done

Three deliverables, all landed this session:

1. **Frozen double-click UX + `--report` + localized filename** (ADR-017,
   `report_name.py` + `cli.py`). A double-clicked binary (gated on
   `sys.frozen` **and** no args) scans → writes a self-contained HTML report →
   opens it; the CLI text default is untouched. `--report` exposes the same
   one-shot from a terminal. The **default filename is localized by OS language**
   (`en → machine_inventory`, `pt → inventario_de_maquina`, + es/fr/de, English
   fallback) — **filename only, content stays English**. Pure stdlib, never
   raises. **+12 offline tests** (`test_report_name.py` + 5 CLI routing tests).
2. **PyInstaller one-file spec + Windows binary** (ADR-018,
   `build/machine_scanner.spec` + `build/entrypoint.py`). One spec → one binary
   per OS (names itself `machine-scanner-{windows.exe,linux,macos}` from the
   build OS). `pyinstaller` is a build-time-only `[build]` extra (ADR-001: psutil
   stays the single runtime dep, not in `requirements.txt`). **Built + verified
   live on this Windows box** (see below).
3. **Release workflow** (`.github/workflows/release.yml`) — tag-triggered (`v*`),
   builds on windows/ubuntu/macos-latest, **per-OS smoke test asserts `--list`
   shows all 16**, uploads the three to a GitHub Release. Separate from `ci.yml`
   (no test-matrix duplication). Plus the **USB-stick layout doc** (rewritten
   `build/README.md`: three binaries + `src/` Python fallback + plug-into-
   anything usage + unsigned/first-run caveats).

### Verified (F5, Windows live)
Built `dist/machine-scanner-windows.exe` (**7.4 MB**) and ran it from a **clean
shell (no venv, no PYTHONPATH)**: `--list` → **all 16 collectors**, exit 0 (the
self-registration risk, ADR-002/018, cleared); `--json` exit 0; `--html -o`
→ `<!doctype html>`, **0 external refs** (ADR-015 holds frozen); `--diff` of two
UTF-8 scans → exit 0, diff rendered; `--report` exit 0. **No-args double-click on
this pt-BR box wrote `inventario_de_maquina.html`** (localized!) and opened it,
exit 0. Startup: ~15 s cold (one-file temp-extract + Defender), ~3 s warm.
**Linux + macOS binaries are NOT buildable here** (no Mac; WSL has no `pip`) —
they are produced by the release workflow's runners on a `v*` tag. **239 tests
green** (was 227 pre-F5; +12 F5 tests). CI untouched (no new runtime dep; all
new tests offline).

## Prior phase (F4) — reference

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

## Post-F5 polish (2026-06-12) — brand + release

- **Brand assets landed** (from the better source logos in
  `(private career repo)`, processed with Pillow — crop to the bright cyan
  inner cube, contrast/saturation boost, **bolded for the small sizes so the
  mark survives at 16 px**): `build/machine_scanner.ico` (multi-res 16–256,
  auto-embedded by the spec, rebuilt + confirmed in the Windows exe),
  `assets/logo.png` (README hero — full hypercube, tagline cropped off), and the
  **HTML report favicon** inlined as a `data:` URI (ADR-015 favicon addendum;
  self-containment test refined to allow `data:` URIs, +1 test → **240 green**).
- **README polished**: hero image, badges (CI / release / python / platform /
  license), a **Download** table pointing at the Releases binaries, the
  double-click UX note, F5 marked ✅.
- **GitHub topics set** (hardware-inventory, system-information, cross-platform,
  cli, python, psutil, pyinstaller, diagnostics, sysadmin, clean-room, …).

## Next step

- **Cut `v0.1.0`** (validate-then-tag): run `release.yml` via `workflow_dispatch`
  first to confirm the 3-OS build (no public artifact), then push the tag to mint
  the GitHub Release with `machine-scanner-{windows.exe,linux,macos}`. The
  Windows binary is verified locally; the Linux/macOS ones come from the runners.
- **Demo GIF** of a scan + the HTML report — deferred to Jorge's personal machine.
- A **refined high-contrast square logo variant** would sharpen the 16 px icon
  further (the current crop is good, not perfect); drop a new `.ico` in and the
  spec picks it up. Parked under ROADMAP Ideas: full report-content i18n.

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
