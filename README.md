<p align="center">
  <img src="assets/logo.png" alt="machine_scanner" width="440">
</p>

<h1 align="center">machine_scanner</h1>

<p align="center"><em>Drop it on a USB stick, plug it into any machine, know exactly what it is.</em></p>

<p align="center">
  <a href="https://github.com/JorgeEd13/machine_scanner/actions/workflows/ci.yml"><img src="https://github.com/JorgeEd13/machine_scanner/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/JorgeEd13/machine_scanner/releases/latest"><img src="https://img.shields.io/github/v/release/JorgeEd13/machine_scanner?include_prereleases&sort=semver" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey" alt="Platforms">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"></a>
</p>

A **portable, cross-platform machine inventory tool**. Plug it into any machine
(Windows / Linux / macOS) and get a complete inventory of its **hardware, OS and
network** — as plain text, JSON, or an **interactive, self-contained HTML
report**. It can also **diff two saved scans** to show what changed on a machine
over time.

Built for the "I need to know exactly what this box is" moment: auditing an
unfamiliar machine, capturing a baseline before changes, or sizing a machine
for a workload — without installing an agent or having admin rights.

```
$ machine-scanner
================================================================
  machine_scanner v0.1.0 — machine inventory
================================================================
host     : DGP-05  (monitoramento)
os       : Windows-10-10.0.19045-SP0
scanned  : 2026-06-11T09:16:07-03:00
elevated : False

[System] [ok]
  os: windows ...
[CPU] [ok]
  cores_physical: 2   cores_logical: 4   usage_percent: 26.9 ...
[Memory] [ok]
  total_gb: 7.92   available_gb: 1.05   percent_used: 86.7 ...
[Disk] [ok] ...
[Network] [ok]
  primary_ip: 192.168.100.115 ...
[GPU] [n/a]
```

## Why

A single compiled binary only runs on the OS it was built for — there is no one
file that boots on Windows, Linux and macOS alike. `machine_scanner` solves the
"plug into anything" goal the realistic way: **one codebase, one binary per OS
on the same stick**. The same Python script also runs anywhere Python is
present.

## Download

Grab the binary for your OS from the
[**latest release**](https://github.com/JorgeEd13/machine_scanner/releases/latest)
— no Python, no install:

| OS | Binary | Run |
|----|--------|-----|
| Windows | `machine-scanner-windows.exe` | **Double-click** it, or run from a terminal |
| Linux   | `machine-scanner-linux`       | `chmod +x machine-scanner-linux && ./machine-scanner-linux` |
| macOS   | `machine-scanner-macos`       | `chmod +x machine-scanner-macos && ./machine-scanner-macos` |

**Double-clicking the binary** (no arguments) scans the machine, writes a
self-contained HTML report next to itself, and opens it in your browser — the
filename follows the OS language (`machine_inventory.html`, or
`inventario_de_maquina.html` on a PT-BR box). From a terminal you get the full
CLI below. The binaries are **unsigned**, so SmartScreen / Gatekeeper may warn
on first run — expected for an open-source tool; the source and the build
workflow are right here in the repo. Drop all three on a stick and you have a
scanner for any machine you meet. See [`build/README.md`](build/README.md).

## Install / run

From source (any OS with Python ≥ 3.9):

```bash
pip install -r requirements.txt          # psutil
pip install -e .                          # exposes the `machine-scanner` command
machine-scanner                           # or: python -m machine_scanner
```

No install, straight from the repo:

```bash
PYTHONPATH=src python -m machine_scanner
```

## Usage

```bash
machine-scanner                      # human-readable report to stdout
machine-scanner --json               # machine-readable JSON
machine-scanner --html -o report.html   # interactive, self-contained HTML
machine-scanner --report             # write an HTML report and open it (one-shot)
machine-scanner --only cpu,memory,network
machine-scanner --list               # list available collectors

# Diff two previously saved JSON scans ("what changed on this machine"):
machine-scanner --json -o monday.json
# ...later...
machine-scanner --json -o friday.json
machine-scanner --diff monday.json friday.json          # text diff (default)
machine-scanner --diff monday.json friday.json --html -o changes.html
machine-scanner --diff monday.json friday.json --json   # the diff as JSON
```

The HTML report is a **single self-contained file** — inline CSS and vanilla
JS, no external assets — with **collapsible sections, a search/filter box, and
copy-as-JSON** (per section or the whole scan). With JavaScript disabled it
still renders as a readable static page (collapse falls back to native
`<details>`). The `--diff` mode loads two saved JSON scans (it never re-scans)
and reports sections added/removed and field-level changes.

Some details (BIOS/board serials, full disk SMART, deeper network) require
admin/root; the report states whether the scan ran `elevated` so missing fields
are explainable rather than silent.

## What it collects

| Collector     | Status | Detail |
|---------------|--------|--------|
| `system`      | ✅ | OS, kernel/build, architecture, hostname, uptime, privilege level |
| `cpu`         | ✅ | model, physical/logical cores, frequency, live utilization |
| `memory`      | ✅ | RAM + swap totals and usage |
| `disk`        | ✅ | mounted partitions, filesystem, free space (psutil view) |
| `storage_devices` | ✅ | physical drives — model / serial / firmware / size / bus (NVMe·SATA·USB) / media (SSD·HDD) / SMART health — Windows `MSFT_PhysicalDisk`, Linux `lsblk`/`smartctl`, macOS `diskutil` |
| `network`     | ✅ | interfaces, MAC / IPv4 / IPv6, link state & speed, primary IP |
| `gpu`         | ✅ | all vendors — Windows CIM / Linux `lspci`+sysfs / macOS; NVIDIA enriched via `nvidia-smi` |
| `baseboard`   | ✅ | motherboard / BIOS / serials from SMBIOS — Windows CIM, Linux DMI, macOS `system_profiler` |
| `memory_modules` | ✅ | physical DIMMs (slot / size / speed / type / part #) — Windows CIM, Linux `dmidecode`, macOS |
| `usb`         | ✅ | USB devices (name + VID:PID) — Windows CIM, Linux `lsusb`/sysfs, macOS `system_profiler` |
| `monitors`    | ✅ | displays via EDID (manufacturer / product / serial / name) — Windows `WmiMonitorID`, Linux `/sys/class/drm` EDID, macOS |
| `battery`     | ✅ | charge / status / health — Windows `Win32_Battery`, Linux `power_supply`, macOS `SPPower`; clean "absent" on desktops |
| `input`       | ✅ | keyboards & pointing devices — Windows CIM, Linux `/proc/bus/input` |
| `audio`       | ✅ | sound devices — Windows `Win32_SoundDevice`, Linux `/proc/asound`, macOS `SPAudio` |
| `bluetooth`   | ✅ | radio/adapters **and** paired devices as separate levels — Windows CIM (`PNPClass='Bluetooth'`), Linux `bluetoothctl`+`/sys/class/bluetooth`, macOS `SPBluetooth` |
| `printers`    | ✅ | print queues — Windows `Win32_Printer`, Linux `lpstat` (CUPS), macOS `SPPrinters` |

Output formats: **text** (default), **JSON** (`--json`), **interactive HTML**
(`--html`), plus a **scan diff** (`--diff OLD.json NEW.json`, rendered as text /
HTML / JSON). The JSON doubles as an archivable audit artifact — and as the
input the diff consumes.

## How it works

Each topic is a **collector** that returns a uniform `Section`
(`status` + `data` + `notes`). Collectors self-register; the runner executes
them in isolation — **a failing probe becomes an `error` section and never
aborts the rest of the scan** — and the report renderers walk the sections
generically. Adding a collector is one new module; nothing in the CLI or the
renderers changes. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

`psutil` is the cross-platform backbone (CPU/memory/disk/network); OS-specific
sources (PowerShell CIM / `nvidia-smi` / `lspci` / `lsusb` / `/sys/class/dmi` /
`dmidecode` / `lsblk` / `smartctl` / `bluetoothctl` / `lpstat` /
`system_profiler`) fill the gaps the portable layer can't reach. The tool
degrades gracefully if `psutil` is absent.

The three report renderers and the diff live in `report/` and follow the same
rule as the collectors — they walk `Inventory.sections` generically and never
import a collector. The HTML report is **self-contained** (inline CSS + vanilla
JS, no external assets); the **diff** is a pure, renderer-agnostic comparison of
two saved scans, displayed by separate text/HTML/JSON formatters.

## Roadmap (short)

- **F2** ✅ — deeper per-OS hardware: `baseboard` (motherboard / BIOS / serials),
  multi-vendor `gpu`, and `memory_modules` (per-DIMM).
- **F2.x** ✅ — `storage_devices`: physical drives beyond psutil (bus / media /
  SMART health).
- **F3** ✅ — peripherals: `usb`, `monitors` (EDID), `battery`, `input`, `audio`,
  plus `bluetooth` and `printers`, each a sibling collector.
- **F4** ✅ — interactive, self-contained HTML report (collapse / search /
  copy-as-JSON) + scan diff between two saved scans.
- **F5** ✅ — packaged single-file binaries per OS (PyInstaller), a tag-triggered
  release workflow, and the double-click → HTML report experience.

All numbered phases are complete.

Full plan in [`PLAN.md`](PLAN.md) and [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests run fully offline and make no assumptions about the host's hardware.

## License

MIT — see [`LICENSE`](LICENSE).
