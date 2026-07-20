# ARCHITECTURE — machine_scanner

## The shape in one picture

```
collectors/                 core/                         report/
 system.py   ┐                                             json_report.py
 cpu.py      │  @register    registry.run_all(only)        text_report.py
 memory.py   ├────────────►  ├ import collectors pkg ─►     html_report.py
 disk.py     │  (self-       │  (triggers @register)        diff.py
 network.py  │   register)   ├ build meta (os/host/…)            ▲
 gpu.py …    │               └ run each collector  ──► Inventory ┘ walks sections
 usb/audio/… ┘                  in try/except          (meta, [Section…])  generically
 (16 collectors)                                                  │
                                                                  ▼
                                              cli.py  (text/--json/--html/--diff)
```

`advisor/` is the F6 addition and sits between the two: pure functions that take
a **completed** `Inventory` and derive a new `Section` from several existing ones
at once (`ollama_fit` — which local LLM this machine can run). It probes nothing,
so it is not a collector; `cli.py` appends it after `run_all()`. See ADR-019.

`report/diff.py` is the F4 addition: a **pure** comparison of two saved
`Inventory.to_dict()` scans (`diff_scans`) plus separate text/HTML formatters
that display the diff and never recompute it — the same "compute vs render"
split that keeps the renderers free of collector knowledge.

## Three ideas, and why

### 1. Uniform `Section`, generic renderers

Every collector returns the same shape — a `Section(name, title, status, data,
notes)` — and the whole scan is an `Inventory(meta, sections)`
(`core/models.py`). The renderers (`report/`) **walk sections generically** and
never import a collector. Consequence: **adding a collector touches one file**
(a new module in `collectors/`, listed in its `__init__`). The CLI and all three
renderers pick it up for free. This is the property that keeps the tool easy to
extend as hardware coverage grows.

`Status` is an enum that inherits `str`, so it serializes to a plain string in
JSON with no custom encoder.

### 2. Self-registration + isolated execution

Collectors register themselves at import time with `@register("name")`
(`core/registry.py`). `run_all()` imports the `collectors` package (which
triggers every decorator), then runs each collector **inside a `try/except`**:
a collector that raises becomes an `ERROR` section carrying the traceback, and
the scan **still completes**. A flaky GPU probe must never cost you the CPU and
network inventory. `--only A,B` filters the set; unknown names are ignored.

The runner also stamps the `Inventory.meta` (tool/version, timestamp, OS,
hostname, user, elevation) — single source of the scan's provenance.

### 3. Portable backbone + OS-specific edges

`psutil` provides CPU / memory / disk / network uniformly across OSes — one
dependency instead of three platform code paths. What psutil can't reach (GPU
vendors, BIOS/board serials, peripherals) is gathered by **shelling out to OS
tools** through one guarded helper, `core.platform.run_command`, which swallows
the three failure modes (missing binary, timeout, non-zero exit) and returns
`None`. `gpu.py` (NVIDIA via `nvidia-smi`) was the reference implementation of
that pattern; the F2/F3 collectors follow it for PowerShell CIM / `lspci` /
`lsblk` / `bluetoothctl` / `system_profiler`.

psutil itself is imported lazily via `collectors/_psutil.py`: if it's absent,
the dependent collectors degrade to `PARTIAL`/`UNAVAILABLE` with a clear note
rather than crashing.

## Layering

- `core/` — no knowledge of specific collectors or output formats.
- `collectors/` — depend on `core`; never on `report` or `cli`.
- `advisor/` — depends on `core.models` only; never imports collectors or
  `report`. Derives new sections from a finished `Inventory` (ADR-019).
- `report/` — depend on `core.models` only; never import collectors. The diff
  (`report/diff.py`) computes over plain `to_dict()` dicts and is renderer-
  agnostic; its text/HTML formatters display but never compute.
- `cli.py` — wires registry → advisor → renderer; the only place that knows all.

Dependencies point inward toward `core`; nothing in `core` imports outward.

## Status semantics (honest output)

`ok` (got it all) · `partial` (some fields) · `unavailable` (nothing to collect
here, e.g. no GPU) · `unsupported` (not implemented for this OS yet) · `error`
(the collector raised). The distinction matters: a desktop with no battery
reports `battery=unavailable`, not a failure; a collector with no
implementation for the current OS reports `unsupported` — so an expected gap is
never mistaken for a bug.

## Portability note (the design constraint)

A compiled binary is OS-specific; there is no universal executable. The codebase
is therefore written once and **packaged per OS** (F5). The pure-Python entry
point (`python -m machine_scanner`) is the fallback that runs anywhere Python
exists.
