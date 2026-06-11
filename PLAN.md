# PLAN — machine_scanner

A public, clean-room portfolio project: a **portable, cross-platform machine
inventory tool**. Goal: a navigable, runnable repo that demonstrates systems
programming, clean cross-platform Python and a tidy plugin architecture — the
kind of utility you can drop on a USB stick and run against any machine.

The idea grew out of a private hardware-detection helper (used to size a machine
for local LLMs), generalized into a standalone, public tool that maps **all** of
a machine's hardware, OS and network — not just RAM/GPU.

## Principles

- **English everywhere**; clean room (reimplement, never copy private code/data).
- **Plan first**; record non-obvious choices as ADRs in `docs/DECISIONS.md`.
- A great README and a clean architecture count as much as the feature count.
- **Graceful everywhere**: missing dep, missing privilege, missing device — the
  scan always completes and explains the gaps.

## The reality check (scope-defining)

There is **no single binary that runs on every OS**. A PyInstaller `.exe` runs
only on Windows. So the "plug into any machine" goal is delivered as **one
codebase → one binary per OS on the same stick** (plus the raw Python script
wherever Python exists). This is baked into the architecture and the F5 plan.

## Architecture (target)

```
collectors/* (self-register)  ──►  registry.run_all() [isolated per collector]
        ──►  Inventory(meta, [Section…])  ──►  report.{json,text,html}
                                                         ──►  CLI (-/--json/--html)
```

`psutil` is the cross-platform backbone; OS-specific tools (`nvidia-smi`, WMI,
`lshw`, `system_profiler`) fill what the portable layer can't reach. See
`docs/ARCHITECTURE.md`.

## Phases

### Phase 0 — Foundations & runnable skeleton  ✅
src-layout package; core (`models`, `platform`, `registry`); collectors for
**system, cpu, memory, disk, network** (psutil) + **gpu** (NVIDIA via
`nvidia-smi`) + **peripherals** (registered stub); json/text/html renderers;
`machine-scanner` CLI (`--json/--html/--only/--list/--out`); offline pytest
(10 passing); README, CLAUDE, docs skeletons, MIT license, pyproject. Verified
end-to-end on Windows.

### Phase 1 — Hardening & ergonomics
Richer text layout (nested tables for interfaces/partitions), `--only` groups,
exit codes, more edge-case tests (no-psutil path, error isolation), CI
(GitHub Actions: pytest on Linux + Windows). Cross-OS smoke run (Linux/WSL).

### Phase 2 — Deeper hardware (per-OS)
GPU beyond NVIDIA (AMD/Intel/integrated); motherboard / BIOS / RAM-slot /
serials via WMI (Windows), `dmidecode`/`lshw` (Linux), `system_profiler`
(macOS). Honest privilege handling (note when elevation would add fields).

### Phase 3 — Peripherals & extras
USB devices, monitors, input devices, battery/sensors. Each is a collector
following the F2 per-OS command pattern.

### Phase 4 — Richer HTML report
Interactive single-file report (collapsible sections, search, copy-as-JSON);
optional diff between two scans ("what changed on this box").

### Phase 5 — Packaged binaries (the USB-stick deliverable)
PyInstaller one-file builds per OS (`build/` specs), a tiny launcher, and a
release workflow that produces `machine-scanner-{win,linux,macos}` artifacts.

## MVP cut

Phases 0–1 plus the start of Phase 2 (one extra GPU vendor or board info) is a
strong, honest showcase. Phases 3–5 are clearly-scoped extensions.

## Out of scope (for now)

- Remote/fleet scanning or a central database — this is a local, single-host
  tool by design.
- Active network scanning (port scans of other hosts) — inventory of *this*
  machine only, to stay unambiguously a benign diagnostic tool.
