# machine_scanner

A **portable, cross-platform machine inventory tool**. Drop it on a USB stick,
plug it into any machine (Windows / Linux / macOS), and get a complete
inventory of its **hardware, OS and network** — as plain text, JSON, or a
self-contained HTML report.

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
machine-scanner --html -o report.html
machine-scanner --only cpu,memory,network
machine-scanner --list               # list available collectors
```

Some details (BIOS/board serials, full disk SMART, deeper network) require
admin/root; the report states whether the scan ran `elevated` so missing fields
are explainable rather than silent.

## What it collects

| Collector     | Status | Detail |
|---------------|--------|--------|
| `system`      | ✅ | OS, kernel/build, architecture, hostname, uptime, privilege level |
| `cpu`         | ✅ | model, physical/logical cores, frequency, live utilization |
| `memory`      | ✅ | RAM + swap totals and usage |
| `disk`        | ✅ | mounted partitions, filesystem, free space |
| `network`     | ✅ | interfaces, MAC / IPv4 / IPv6, link state & speed, primary IP |
| `gpu`         | ◐ | NVIDIA via `nvidia-smi`; AMD/Intel/integrated planned (F2) |
| `peripherals` | ◻ | USB / monitors / input devices — planned (F3) |

Output formats: **text** (default), **JSON** (`--json`), **HTML** (`--html`).
The JSON doubles as an archivable audit artifact.

## How it works

Each topic is a **collector** that returns a uniform `Section`
(`status` + `data` + `notes`). Collectors self-register; the runner executes
them in isolation — **a failing probe becomes an `error` section and never
aborts the rest of the scan** — and the report renderers walk the sections
generically. Adding a collector is one new module; nothing in the CLI or the
renderers changes. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

`psutil` is the cross-platform backbone (CPU/memory/disk/network); OS-specific
tools (`nvidia-smi`, and later WMI / `lshw` / `system_profiler`) fill the gaps
the portable layer can't reach. The tool degrades gracefully if `psutil` is
absent.

## Roadmap (short)

- **F2** — GPU beyond NVIDIA; motherboard / BIOS / RAM-slot detail (per-OS).
- **F3** — peripherals (USB, monitors, input).
- **F4** — richer interactive HTML report.
- **F5** — packaged single-file binaries per OS (PyInstaller) for the USB-stick workflow.

Full plan in [`PLAN.md`](PLAN.md) and [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests run fully offline and make no assumptions about the host's hardware.

## License

MIT — see [`LICENSE`](LICENSE).
