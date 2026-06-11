# STATE — machine_scanner

> Volatile, short. Update at the end of each step.

**Date:** 2026-06-11
**Phase:** F1 (hardening + CI) — ✅ done. Next: F2 (deeper per-OS hardware).

## Current focus

F1 closed. The tool is now CI-backed and cross-OS verified: nested data reads
cleanly in text mode, the no-psutil path is tested, exit codes are meaningful,
and a GitHub Actions matrix runs the suite on ubuntu + windows. 24 tests green
locally (was 10).

## Done (F1)

- **Recursive text renderer** (ADR-007): `report/text_report.py` now descends to
  any depth — network interface addresses / disk partitions print as an indented
  outline instead of a Python `repr`. `str`/`bytes` treated as scalars. Verified
  on a live Windows scan (`--only network,disk`).
- **No-psutil path** (`tests/test_no_psutil.py`): monkeypatches `_psutil.get →
  None` and asserts each collector's documented fallback (network→PARTIAL,
  disk/memory→UNAVAILABLE, cpu→PARTIAL keeping `os.cpu_count`) and that **none**
  raise. The WSL run below exercised this for real (Ubuntu has no psutil).
- **Exit codes** (ADR-008): `cli.main` returns `0` clean / `2` if any section is
  `ERROR`; expected gaps (partial/unavailable/unsupported) stay `0`. Covered by
  `tests/test_cli.py` plus output-path tests (`--list`, `--json`).
- **CI**: `.github/workflows/ci.yml` — matrix `{ubuntu, windows} × {3.9, 3.13}`,
  `pip install -e .[dev]`, `pytest -v`, then a CLI smoke run (`--list`, text,
  `--json`). **Observed GREEN on all 4 GitHub jobs** (run 27347587254, ~1m20s,
  2026-06-11). Bumped `actions/checkout@v5` + `setup-python@v6` to clear the
  Node-20 deprecation (forced to Node 24 on 2026-06-16).
- **Cross-OS smoke run**: WSL Ubuntu (Python 3.12) ran `python -m
  machine_scanner` end-to-end — Linux OS detection correct, graceful psutil-less
  degradation, no crashes.

## Next step (F2 — deeper hardware)

1. First deep collector beyond psutil, via `core.platform.run_command`:
   candidates — motherboard/BIOS/serials (WMI on Windows, `dmidecode`/`lshw` on
   Linux, `system_profiler` on macOS), or GPU beyond NVIDIA (AMD/Intel/iGPU).
2. Must degrade to `unsupported`/`partial` on other OSes and note elevation
   needs. Add a focused offline test + an ADR if a non-obvious choice is made.

## Notes / open points

- CI **confirmed green on GitHub** (4 jobs) — F1 DoD fully met.
- `gpu` still `[n/a]` on this i3 box (no NVIDIA) — expected.
- WSL has no `pip`, so pytest wasn't run there; CI's ubuntu job covers
  pytest-on-Linux. The WSL CLI run was enough to confirm cross-OS execution.
