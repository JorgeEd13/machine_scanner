# STATE — machine_scanner

> Volatile, short. Update at the end of each step.

**Date:** 2026-07-20
**Phase:** F6.1 (the requirements checker as its own binary) — ✅ **closed**.
F0–F6.1 all done. ADR-021 (a second, scoped binary — the privacy claim is a
property of the artifact) and ADR-022 (requirement bars are fixed and published)
for the choices; F6's are ADR-019/020.

## Current focus (F6.1) — done

> 🧊 **FROZEN for feature work since 2026-10-03 — study block open.** This repo was cut into
> **14 territories** by the APROFUNDAMENTOS programme (`repo-base-career/sistema/APROFUNDAMENTOS_ROADMAP.md`
> §R3). While the block is open, that programme reads this code line by line and measures its
> guards by mutation, so a moving tree would invalidate the measurements. Findings from the study
> go to this file's backlog rather than being fixed there. The freeze lifts when the R3 block
> closes. It is a *convention*, not a mechanism — nothing enforces it; Jorge can lift it by saying so.


**`ai-model-requirements-{windows.exe,linux,macos}`** — a second one-file binary
for someone who was *sent* it and has no reason to trust it yet.

- **It reads five things** (cpu, memory, gpu, disk, `llm_runtime`) and strips
  `hostname`/`user` from the metadata. **The full scan is ~13,000 characters, of
  which ~4,300 bear on the decision** — the rest is hostname, username, primary
  IP, MAC addresses, disk serials, monitor codes and the USB device list.
- **Separate binary, not a flag,** so the spec can **exclude** the other twelve
  collector modules: "it cannot read your serial numbers" is then checkable
  against the artifact rather than a promise about how it was invoked.
- **New `llm_runtime` collector** — is Ollama installed? is Docker? Presence on
  disk only, nothing executed (`ollama --version` contacts the local server and
  can hang). The answer **raises the free-disk bar** by whichever install is
  missing, and the report says why.
- **Fixed Minimum / Recommended bars** (ADR-022), in the shape of game system
  requirements. A minimum derived from the machine being measured can never be
  failed — that was the trap. Memory passes by **either** route (card *or* RAM);
  a **disk-only** blocker reads `NOT YET`, not `NO`, because that is a ten-minute
  fix rather than a purchase; and a failing machine is never handed a "best
  available to you" line, which under a `NO` reads as a contradiction.
- **Refactor it forced:** the load manifest moved from `collectors/__init__.py`
  to `collectors/_all.py` (the package now imports nothing), plus
  `run_all(autoload=False)`. Importing one collector no longer imports all 17.

### ⚠️ Three bugs found by the first real Windows run (2026-07-20) — all fixed
A live **8 GB Windows box read `NO`**; it should have read `YES, WITH LIMITS`.
1. **RAM bars compared sticker GB against reported GB.** A machine never reports
   the size it was sold as: that box reported **7.9** against an **8 GB** bar, and
   a 16 GB laptop with an iGPU reports **14.6** against 16. The bars rejected the
   machines they were written to admit. Fixed by `nominal_ram_gb` (round up to a
   standard size only within 12%); the reported figure stays visible, and `fit`
   still sizes on real memory.
2. **The range line contradicted the table** — "It has the memory for a model"
   printed under a memory blocker. Now emitted only when all blockers are soft.
3. **HTML is now pure ASCII** (numeric entities). The page travels by email and
   chat through tools that ignore `<meta charset>`; an em dash read as cp1252
   becomes `â` — ADR-016's failure mode, in the one file we hand to strangers.

**307 tests green** (was 300; +7 regression tests, each named for the machine
that found it). **None of these were reachable from tests written by the person
who chose the thresholds** — they needed someone else's real hardware.

### Verified (F6.1, Linux live — both binaries built)
Qualifier **9.4 MB**; `strings` confirms **none** of the twelve excluded
collectors are in it. Full scanner still lists **17**. The delivered HTML page
grepped against this machine's hostname, username and IP → **none present**.
Self-contained (0 external refs), brand mark inline. **300 tests green** (was
269; +34 offline).
⚠️ **Windows smoke-test bug (fixed 2026-07-20, first `workflow_dispatch` run):**
the PowerShell verdict check used `if ($out -notmatch ...)`, but `&` yields a
string array and `-notmatch` on an array *filters* rather than returning a
boolean — so it failed a **working** binary, unconditionally. Now
`Select-String -Quiet`, and it prints the output on failure. The `--list`==17
assertion **passed on Windows**, which confirms the PyInstaller `_all` fix holds
there too.

⚠️ **The smoke test earned its keep:** the first frozen build of the *full*
scanner registered **zero** collectors — the registry reaches `_all.py` via
`importlib.import_module`, invisible to PyInstaller's static analysis. One
`hiddenimports` entry fixed it. Exactly the ADR-002 risk, which is why the
release workflow asserts a **count** and not a clean exit.

## Prior phase (F6) — reference

A new pure layer, `src/machine_scanner/advisor/`, answers *"which local LLM can
this machine run?"* from a completed scan:

- **`catalog.py`** — 9 public Ollama chat models × {RAM, VRAM, download size,
  coarse quality rank}, plus the capability bands
  (`unusable` / `minimal` / `workable` / `comfortable`).
- **`fit.py`** — pure `Inventory → Section`. Usable memory = **VRAM** where a
  *discrete* GPU can accelerate, else **80% of system RAM**. Ranks the catalog
  against memory **and free disk**.
- **`summary.py`** — the short pasteable verdict (`--ollama`), display-only.
- **CLI** — `ollama_fit` rides along with every full scan (and the double-click
  HTML report); `--only` filters it like a collector; `--ollama` prints just the
  verdict.

**Why not a 17th collector (ADR-019):** a collector is zero-arg and cannot see
its siblings, but this question spans cpu + memory + gpu + disk at once — a
collector could only answer it by re-detecting all four, duplicating the most
OS-specific code in the repo. Deriving instead of probing also makes every
branch testable from a synthetic `Inventory`.

**Three traps the naive heuristic falls into**, all handled and all tested:
integrated GPUs counted as VRAM (double-counts system RAM); Windows
`AdapterRAM` saturating at 4 GB (a 16 GB card reads as 4 — degrades
conservatively, with a note); disk blocking a model that memory allows.

### Verified (F6, Linux live)
Hybrid-GPU laptop (Intel Raptor Lake iGPU + **RTX 4050**): the iGPU is correctly
**excluded**, the box is sized on the 4050's **6.0 GB VRAM** → verdict
`comfortable`, best fit `qwen2.5:7b`, 5 of 9 models fitting. HTML report still
**0 external refs**; `--only memory` correctly omits the section. **269 tests
green** (was 240; +29 offline).

## Prior phase (F5) — reference

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
green at the time of F5** (was 227 pre-F5; +12 F5 tests). CI untouched (no new
runtime dep; all new tests offline). *(Superseded: the count is now **240** —
see the brand-assets entry below, which added one test. Verified by
`pytest --collect-only`: 240 collected, 240 passed.)*

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
  a private asset folder, processed with Pillow — crop to the bright cyan
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

- **Study-block findings — R3-T1 (2026-10-03).** Backlog only; the repo is frozen
  (see top), so none of these is fixed yet. Measured against `38803b5`, 317 tests.
  - **Status honesty.** `system` returns `ok` without psutil (no `boot_time` /
    `uptime_hours`); `memory` returns `ok` with no note and no swap keys when
    `swap_memory()` raises (`except Exception: pass`). `docs/ARCHITECTURE.md` defines
    that as `partial` ("some fields"). `cpu`/`disk` also return `ok` with a field
    missing (with a note); `network` returns `ok` with `primary_ip: null` and no note. `Section.status` defaults to `OK`, so forgetting reads as success.
  - **`--only` typo.** `--only cpuu --json` → 0 sections, exit 0. `run_all(only=[])`
    runs all 17 (empty list is falsy). Validate names at the CLI.
  - **Per-collector time bound.** Isolation is `try/except` only: a collector that
    blocks delays every later one, and psutil calls have no timeout (only
    `run_command` does). "The scan always completes" holds for raising, not hanging.
  - **`run_command` outcome.** Missing binary, timeout, non-zero exit and a str
    argument containing a space (`"ls -l"`, read as one binary name) all return `None`; empty successful output
    returns `""`. Callers cannot tell `unavailable` from `error`.
  - **Test gaps.** Deleting `check=True` → 317 green. Widening the runner's catch to
    `BaseException` → 317 green (Ctrl+C becomes an `ERROR` section and the scan
    continues). `encoding="utf8"` (same codec) → red: the test asserts the keyword,
    not decoding. A duplicate `@register` name is accepted silently and caught only
    by `test_only_filters_collectors`.
- **Study-block findings — R3-T2 (2026-10-03), `baseboard` + `_smbios`.** Backlog only;
  repo frozen. Measured against `4765464`, 317 tests; mutations run on a copy.
  - **`baseboard` duplicates `_smbios`.** It predates the helper and never migrated: its own
    `_PLACEHOLDERS` (23 entries vs 24 — `"no module installed"` exists only in `_smbios`), its
    own `_clean`, its own PowerShell call without `_strip_bom` or list normalization. A
    BOM-prefixed output → `unavailable`; JSON `null` / `[]` / `[{}]` → `AttributeError` from
    `.items()`, not caught by `except (ValueError, TypeError)`, so the runner records `error`
    (the module docstring says it never raises for an expected-absent case). Expected to be
    latent — a single `pscustomobject` should serialize as an object — but not checked on a real
    PowerShell. Fix: use `_smbios.clean` / `run_cim`.
  - **Array-valued CIM fields.** If a class returns two instances, PowerShell member
    enumeration makes the field an array and `_clean` stringifies it: stubbed
    `bios_vendor=["AMI","AMI"]` → `"['AMI', 'AMI']"`. Not observed on real hardware.
  - **Linux privilege flag.** ADR-009 calls `PermissionError` the precise elevation signal;
    the code decides by `is_admin()`, and `blocked_by_privilege` only changes the outcome when
    root is blocked. Removing it → 317 green; no test creates a mode-0400 file (the PARTIAL
    test uses an absent file).
  - **macOS synthesized `"Apple"`.** `setdefault` runs before the status decision, so any
    non-empty `system_profiler` output yields identity: an error line → `ok` with only
    `system_manufacturer` (admin), or `partial` with an elevation note that is wrong (non-admin).
  - **Placeholder coverage.** Tests exercise 7 of the 23 `baseboard` entries. Removing
    `"base board serial number"` → 317 green, and the leaked placeholder then counts as a
    readable serial, which suppresses the elevation note (`ok`, no notes, unprivileged).
  - **`run_cim` contract tests.** Dropping the single-object wrap is caught only by an
    encoding test (`test_run_cim_forces_utf8_prefix_and_strips_bom`); dropping the
    `isinstance(row, dict)` filter → 317 green. Collector tests stub `run_cim` out.
- **Study-block findings — R3-T3 (2026-10-03), multi-vendor `gpu`.** Backlog only; repo
  frozen. Measured against `45c0153`, 317 tests; mutations run on a copy.
  - **Vendor classifier false positive.** `_classify_vendor` matches the tag `"ati"` as a
    substring, so `"Microsoft Corporation"` and `"Oracle Corporation"` → `AMD`, and a stubbed
    `lspci -mm` line `"3D controller" "Microsoft Corporation" "Basic Render Driver"` → vendor
    `AMD`. Removing `"ati"` → 317 green (the AMD test case also contains `"amd"`). Fix: match
    tokens with word boundaries; add a negative test case.
  - **NVIDIA merge drops cards.** `collect()` discards *every* NVIDIA row from the generic
    enumerator whenever `nvidia-smi` returns anything. Stubbed 2 enumerated NVIDIA cards + 1
    `nvidia-smi` row → 1 card reported, status `ok`, no note. Fix: join on PCI bus id
    (`--query-gpu=pci.bus_id`), or at least keep the surplus / add a note.
  - **Partial enumeration reported as `ok`.** Generic enumerator fails (`None`) but
    `nvidia-smi` works → `ok` with the "could not enumerate" note attached; non-NVIDIA
    adapters are silently missing. Should be `partial`.
  - **No test asserts on the `nvidia-smi` parser.** The `collect()` unit tests stub
    `_query_nvidia` out; only the real-host smoke test runs it (on a host that has
    `nvidia-smi`), and it asserts nothing about the parsed rows. Relaxing the
    column check `!=` → `<` → 317 green, and a 6-column line then makes `zip(strict=True)`
    raise `ValueError` out of `collect()`. `[N/A]` fields stay strings next to floats
    (`temperature_c: '[N/A]'`).
  - **Advisor ↔ `gpu` contract.** `advisor/fit.py` assumes a row with `driver_version` came
    from `nvidia-smi`, but the Windows enumerator also sets `driver_version`. Stubbed CIM row
    (AMD, `AdapterRAM` = 4 GiB − 1, a driver version) → `_pick_gpu` emits no 4 GB caveat; the
    same row without `driver_version` gets it. Also applies to NVIDIA rows on Windows when
    `nvidia-smi` is absent. The `gpu` section still carries its own `AdapterRAM` note.
    Checked through `_pick_gpu` only.
- **Study-block findings — R3-T4 (2026-10-03), `memory_modules`.** Backlog only; repo
  frozen. Measured against `1c6c91c`, 317 tests; mutations run on a copy.
  - **Memory-type table mixes two code spaces.** `_DDR_TYPES` is applied to
    `SMBIOSMemoryType` (SMBIOS type-17 codes), but its 20 → `DDR` and 21 → `DDR2` entries
    look like WMI's own `MemoryType` enum (per Microsoft's docs; not checked on Windows). Synthetic SMBIOS dumps decoded by `dmidecode 3.6`
    give 18 = DDR, 19 = DDR2, 20 = DDR2 FB-DIMM, 21 = Reserved; `_type_label` returns
    `type 18`, `type 19`, `DDR`, `DDR2`. Codes 24/26/34 agree, and those are the ones the
    test samples. The table is not used on Linux, which passes `dmidecode`'s decoded string
    through, so for codes 20/21 the two platforms disagree (`DDR2 FB-DIMM` / `Reserved` on
    Linux). Fix: SMBIOS codes, plus a test case in the 18–21 range.
  - **Apple Silicon docstring.** The module docstring says unified memory "reports as a
    single entry with no slot"; with a stubbed Apple-Silicon-shaped `SPMemoryDataType` output
    (`Memory: 16 GB` / `Type: LPDDR5`, no `DIMM`/`BANK` header; shape assumed, not captured
    on a Mac) the collector returns `unavailable` with `modules: []`.
  - **"Run as root" regardless of privilege.** The Linux no-output branch never calls
    `is_admin()`: stubbed `is_admin() = True` + no output → the same "run as root" note. A
    missing `dmidecode` or a timeout gives the same note (see R3-T1, `run_command` outcome).
    `test_linux_needs_root_when_no_output` stubs `is_admin` to `False`, which that branch
    never reads.
  - **Linux fixture omits lines real `dmidecode` prints.** No `Bank Locator`, no
    `Configured Memory Speed: Unknown`, no test with output present and non-root. Adding
    `"Bank Locator": "slot"` to `_DMIDECODE_FIELDS` → 317 green, and on real `dmidecode`
    output the slot becomes `BANK 0`. Dropping the `or current.get("speed_mhz")` fallback →
    317 green, and with configured speed `Unknown` the speed becomes `None` (was 2667).
    Deleting the non-root caveat note → 317 green.
- **Study-block findings — R3-T5 (2026-10-03), `usb` + `bluetooth`.** Backlog only; repo
  frozen. Measured against `6bdbae3`, 317 tests; mutations run on a copy.
  - **The sysfs-fallback note says "no device names", but the path reads them.**
    `_collect_linux` (usb) adds `lsusb unavailable; read /sys/bus/usb (no device names)`,
    while `_parse_sysfs_usb` reads each device's `product` and `manufacturer` files. On this
    Linux host with `lsusb` stubbed out (host state at the time of the run): 10 devices, all
    10 named, plus that note.
  - **Bluetooth connection nodes counted as adapters.** `_read_sysfs_adapters` keeps every
    entry whose name starts with `hci`. The kernel is understood to also create `hciX:<handle>` entries under
    `/sys/class/bluetooth` for active connections (not captured or checked on this host); a tmp tree
    with `hci0` + `hci0:3585` returns two adapters. The usb sysfs reader skips names with
    `:`; this one has no such guard.
  - **The Linux adapter address is never read on this host.** `_read_sysfs_adapters` reads
    `/sys/class/bluetooth/hciX/address`; on this host `hci0` has no `address` file (observed
    on kernel 7.0 / BlueZ 5.85; not checked on other kernels), so the adapter is reported as `{"name": "hci0"}` only. The tests create
    an `address` file in their tmp tree, which this host's sysfs doesn't have.
  - **Non-empty but unparseable tool output degrades silently** (one stubbed string per
    collector; exit codes of the real tools in these cases not checked). `bluetoothctl` printing one
    line that isn't a `Device` line (stubbed: `No default controller available`) → `ok`,
    `device_count` 0, **no note**; the "no paired-device list" note only fires on empty
    output. Same shape in usb: stubbed `lsusb` output that matches no line → `unavailable`
    with no note and the sysfs fallback skipped.
  - **Windows Bluetooth: unknown rows default to "adapter".** `_classify_windows` sends
    anything that is neither `DEV_<mac>` nor `BTHENUM…` to `adapters`. Canned rows for the
    radio plus four `BTH\MS_*` enumerator nodes (`MS_BTHBRB`, `MS_BTHLE`, `MS_RFCOMM`,
    `MS_BTHPAN`; IDs written from Windows knowledge, not captured on a Windows host) →
    `adapter_count` 5 for one radio.
  - **Windows USB: composite-device interfaces listed as separate devices.** Rows under
    `USB\VID_xxxx&PID_yyyy&MI_nn` share the parent's VID:PID; one parent + three `MI_`
    rows (canned) → `count` 4, one distinct VID:PID. The Linux sysfs parser skips interface
    (`:`) nodes, so the two OSes would likely count one composite device differently (inferred
    from canned rows and a tmp sysfs tree; no real device counted on both).
  - **Test gaps.** Each of these mutations leaves the 30 usb/bluetooth tests green: removing
    the `:` interface guard in `_parse_sysfs_usb` (the `idVendor` check drops those nodes
    anyway, and the test doesn't check that no file is read); widening the PowerShell
    filter `-like 'USB\*'` → `-like '*USB*'` (no test reads the query string); replacing
    the sysfs fallback in usb `_collect_linux` with `devices = []` (no test drives that
    branch end-to-end).
- ✅ **`v0.2.2` (2026-07-21) — licence names by VERSION.** `v0.2.1` recorded a
  licence per model but named the Llama ones generically. **There is no single
  "Llama Community License": 3.1, 3.2 and 3.3 are separate agreements**, with
  different required attribution strings and different acceptable-use-policy
  URLs, so a reader who took the generic name and went looking would land on the
  wrong document. **That is not hypothetical** — reading a Llama *3* licence for
  a Llama *3.1* model is the mistake the private counterpart nearly shipped, and
  it matters: Llama 3 §1.b.v forbids using outputs to improve another LLM, and
  **3.1 and 3.2 dropped that clause**. Naming the nearest version imposes a
  restriction the user's licence does not contain. Strings only — no behaviour
  change, 311 tests unchanged.
- ✅ **`v0.2.1` (2026-07-21) — model LICENCES.** Every catalog entry now carries
  its licence, and a model that may not be used commercially is **listed but
  never recommended**. `qwen2.5:3b` is the case: every other Qwen2.5 size here is
  Apache-2.0 and the 3B is under a research licence — and it is the highest-quality
  model that fits a modest 4 GB machine, so it was precisely the one this tool
  headlined. **Open weights are not open source**, and "free to download" is not
  "free to use at work". The restricted row stays visible *with its licence*:
  hiding it would make the tool less honest, not safer. +4 tests (311).
- ✅ **`v0.2.0` PUBLISHED (2026-07-20)** — six artifacts (3 scanner + 3
  qualifier), built from the commit that carries all three Windows fixes.
  Verified live on a real Windows box afterwards: the 8 GB machine now reads
  `YES, WITH LIMITS`, the RAM row shows `8 GB` with `reports 7.9 GB` beneath it,
  and the em dash arrives as `&#8212;` and renders correctly in the browser.
- **macOS is still unverified by a human.** The binary builds and passes its
  smoke test on the `macos-latest` runner, but nobody has double-clicked it.
  **Docker cannot help** — a container shares the host kernel and a Mach-O
  binary needs XNU plus Apple's frameworks; virtualising macOS off Apple
  hardware breaches the licence. **The runner IS real Apple hardware**, so the
  cheap next step is to extend its smoke test: run the default HTML path, then
  `xattr -w com.apple.quarantine` + `spctl --assess --type execute -vv` to
  capture **what Gatekeeper actually says**, so client instructions can quote it
  instead of guessing. The Finder double-click stays untestable (no GUI session).
- **Keep feeding it real machines.** Every bug in the F6.1 round came from
  someone else's hardware; none were reachable from fixtures written by whoever
  chose the thresholds. A box with a discrete AMD GPU, or one with 4 GB of RAM,
  would be the next most informative.
- ~~**Cut `v0.1.0`** (validate-then-tag)~~ — superseded by v0.2.0: run `release.yml` via `workflow_dispatch`
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
