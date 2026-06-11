# STATE — machine_scanner

> Volatile, short. Update at the end of each step.

**Date:** 2026-06-11
**Phase:** F0 (Foundations & runnable skeleton) — ✅ done. Next: F1 (hardening + CI).

## Current focus

Scaffold complete and **verified running on Windows** (Python 3.13, psutil
7.2.2): all 7 collectors register; text / JSON / HTML / `--only` all work;
`pytest` is 10/10 green. The architecture (self-registering collectors →
isolated runner → generic renderers) is proven end-to-end.

## Done (F0)

- **Package** in src-layout (`src/machine_scanner/`), `pyproject.toml` exposing
  the `machine-scanner` console script, `requirements.txt` (psutil).
- **Core:** `models.py` (`Section`/`Inventory`/`Status`), `platform.py`
  (`current_os`, `is_admin`, guarded `run_command`), `registry.py`
  (`@register`, `run_all` with per-collector error isolation + scan metadata).
- **Collectors:** `system` (stdlib-only), `cpu`, `memory`, `disk`, `network`
  (psutil), `gpu` (NVIDIA via `nvidia-smi`), `peripherals` (registered stub).
  `_psutil.py` makes psutil an optional, gracefully-degrading import.
- **Reports:** `json`, `text`, `html` (self-contained, inline CSS). Renderers
  walk sections generically.
- **CLI:** `--json` / `--html` / `--only A,B` / `--out FILE` / `--list` /
  `--version`; UTF-8 stdout reconfigure on Windows.
- **Tests:** `tests/test_models.py` + `tests/test_registry.py` — 10 passing,
  offline, hardware-agnostic (incl. the failing-collector isolation test).
- **Docs/meta:** README, CLAUDE.md, PLAN.md, ROADMAP, ARCHITECTURE, DECISIONS,
  MIT LICENSE, .gitignore.

## Next step

1. **F1 — hardening:** nicer text rendering of nested lists (interface
   addresses currently print as a Python repr in text mode — JSON/HTML are
   fine); add a no-psutil test path; **GitHub Actions** running `pytest` on
   Linux + Windows. Do a smoke run on Linux/WSL to confirm cross-OS.
2. Then **F2** — first deeper-hardware collector (GPU beyond NVIDIA, or
   motherboard/BIOS via WMI/`dmidecode`).

## Notes / open points

- Verified only on Windows so far; Linux/macOS paths are written but **not yet
  run** (F1 smoke run will confirm). `gpu` returned `[n/a]` here (no NVIDIA on
  the i3 box) — expected.
- No `git init` yet at time of writing → done as the final F0 step.
