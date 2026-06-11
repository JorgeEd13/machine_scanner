# STATE — machine_scanner

> Volatile, short. Update at the end of each step.

**Date:** 2026-06-11
**Phase:** F2 (deeper per-OS hardware) — ✅ **closed** (3 deep collectors).
Next: **F3** (peripherals) — see the prepared handoff prompt.

## Current focus

F2 is done: three probes now reach *past* psutil into firmware — `baseboard`
(board / BIOS / serials), `gpu` (now multi-vendor: AMD/Intel/iGPU + NVIDIA), and
`memory_modules` (per-DIMM). All per-OS via `run_command`/sysfs, all degrade to
`unsupported`/`unavailable` without raising. **88 tests green** locally (was 24).

## Done (F2)

- **`collectors/baseboard.py`** (ADR-009): board / BIOS / serial + UUID. Windows
  `Get-CimInstance` (not `wmic`); Linux `/sys/class/dmi/id` (no root for
  identity; `PermissionError` on serial = elevation signal); macOS
  `system_profiler`. Placeholder scrub; accurate elevation note.
- **`collectors/gpu.py`** (ADR-010): rewritten to **multi-vendor**. Generic
  enumerator (Windows `Win32_VideoController` CIM; Linux `lspci` → `/sys/class/
  drm` PCI-ID fallback; macOS `SPDisplaysDataType`) + `nvidia-smi` kept as the
  enrichment layer (NVIDIA from smi, the rest from the enumerator). Live: Intel
  HD Graphics with VRAM + driver on this box.
- **`collectors/memory_modules.py`** (ADR-010): per-DIMM (slot / size / speed /
  type / mfr / part #). Windows `Win32_PhysicalMemory`; **Linux `dmidecode -t
  memory`** — no unprivileged sysfs for SMBIOS type 17, so it needs root and
  degrades to `unavailable` + root note (the *inverse* of baseboard); macOS
  `SPMemoryDataType`. Live: 2×4 GB DDR3-1600 = 8 GB on this box.
- **`collectors/_smbios.py`**: shared helper (sibling of `_psutil.py`) — CIM→JSON
  (normalizes PowerShell single-object vs array) + SMBIOS placeholder scrub.
- **Tests**: `test_baseboard.py` (18), `test_gpu.py` + `test_memory_modules.py`
  (46 more) — parse, command-failure → UNAVAILABLE (not ERROR), Linux tmp-dir
  sysfs / dmidecode parse, root-needed degrade, unsupported OS, never-raises.
- **Verified**: live on Windows (baseboard Lenovo SMBIOS; Intel iGPU; DDR3
  DIMMs) and via **WSL2 smoke** (no DMI/lspci/dmidecode → clean `unavailable`
  with accurate notes, no crash).

## Prior phase (F1) — reference

F1 closed earlier: recursive text renderer (ADR-007), no-psutil path, exit
codes (ADR-008), GitHub Actions matrix {ubuntu, windows} × {3.9, 3.13}, WSL
smoke run. Was 24 tests; CI observed green (run 27347587254).

## Next step (F3 — peripherals)

Flesh out the registered `peripherals` stub (currently `unsupported`): USB
devices, monitors, input devices, battery/sensors — per-OS enumeration following
the F2 dispatch shape (`_smbios.run_cim` on Windows, `run_command`/sysfs on
Linux, `system_profiler` on macOS), degrading to `unsupported`/`unavailable`
without raising, with an ADR for any non-obvious source choice. A dedicated
handoff prompt is prepared for the F3 session.

## Notes / open points

- CI should stay green (no new deps; all new tests are offline). Prior runs green.
- `gpu` now reports the **Intel iGPU** on this i3 box (was `[n/a]` when
  NVIDIA-only). `memory_modules` shows the 2×4 GB DDR3 sticks.
- WSL2 exposes no DMI / `lspci` / `dmidecode` → the three deep collectors are
  `unavailable` there (verified); their parse paths are covered by offline
  tmp-dir / canned-output tests instead.
- WSL has no `pip`, so pytest wasn't run there; CI's ubuntu job covers
  pytest-on-Linux. The WSL CLI run was enough to confirm cross-OS execution.
