# STATE — machine_scanner

> Volatile, short. Update at the end of each step.

**Date:** 2026-06-11
**Phase:** F2 (deeper per-OS hardware) — first deep collector ✅ done.
Next: more F2 collectors (GPU beyond NVIDIA) or F3 (peripherals).

## Current focus

F2 opened with the first probe that reaches *past* psutil into firmware: a
`baseboard` collector (motherboard / BIOS / serials, from the SMBIOS/DMI
tables). Windows via PowerShell CIM, Linux via `/sys/class/dmi/id`, macOS via
`system_profiler`, everything else `unsupported` — all degrading without
raising. 42 tests green locally (was 24).

## Done (F2 — first deep collector)

- **`collectors/baseboard.py`** (ADR-009): motherboard / BIOS / serial + UUID.
  - Windows → `Get-CimInstance` (Win32_BIOS / BaseBoard /
    ComputerSystemProduct) → JSON, **not** deprecated `wmic`; 20 s budget.
  - Linux → reads `/sys/class/dmi/id/` files directly (no `dmidecode`, no root
    for identity; `PermissionError` on `*_serial`/`*_uuid` = elevation signal).
  - macOS → `system_profiler SPHardwareDataType`.
  - SMBIOS placeholder scrub ("To Be Filled By O.E.M.", all-`F` UUIDs, …) →
    `None`. Elevation note fires only when *no* serial is readable unprivileged.
- **`tests/test_baseboard.py`** — 18 offline cases: placeholder scrubbing,
  Windows JSON parse + command-failure → UNAVAILABLE (not ERROR), Linux sysfs
  via a tmp dir (incl. missing-serial → PARTIAL + note), macOS parse,
  unsupported OS, and a live "never raises" guard.
- **Verified on Windows** (live: real Lenovo SMBIOS, status `ok`) and via a
  **WSL2 smoke run** (no DMI table there → clean `unavailable`, no crash).

## Prior phase (F1) — reference

F1 closed earlier: recursive text renderer (ADR-007), no-psutil path, exit
codes (ADR-008), GitHub Actions matrix {ubuntu, windows} × {3.9, 3.13}, WSL
smoke run. Was 24 tests; CI observed green (run 27347587254).

## Next step (continue F2 / start F3)

1. Second deep collector — natural pick: **GPU beyond NVIDIA** (AMD/Intel/iGPU),
   following the same per-OS `run_command` + `unsupported` pattern. Or expand
   `baseboard` with RAM-slot population (Win32_PhysicalMemory / DMI type 17).
2. Or jump to **F3 peripherals** (USB / monitors / battery) reusing this
   collector's per-OS dispatch shape.
3. Keep the rule: degrade without raising, focused offline test, ADR if a
   non-obvious choice is made.

## Notes / open points

- New CI run for this push should stay green (no new deps; `baseboard` test is
  offline). F1 run was green (run 27347587254).
- `gpu` still `[n/a]` on this i3 box (no NVIDIA) — expected.
- WSL2 exposes **no** `/sys/class/dmi/id` → `baseboard` is `unavailable` there;
  the sysfs parse path is covered by offline tmp-dir tests instead.
- WSL has no `pip`, so pytest wasn't run there; CI's ubuntu job covers
  pytest-on-Linux. The WSL CLI run was enough to confirm cross-OS execution.
