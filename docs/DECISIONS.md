# DECISIONS — machine_scanner (ADRs)

Architecture Decision Records. Short, append-only. Each: context → decision →
consequences.

## ADR-001 — psutil as the cross-platform backbone

**Context.** CPU / memory / disk / network detection differs per OS. The choices
were: (a) write per-OS subprocess parsing for each, or (b) lean on a portable
library.
**Decision.** Use **psutil** for everything it covers; reserve OS-specific
commands only for what psutil can't reach (GPU vendors, BIOS/board serials,
peripherals).
**Consequences.** One dependency instead of three brittle code paths; far less
parsing of locale-dependent command output. psutil is imported lazily
(`collectors/_psutil.py`) so its absence degrades gracefully instead of
crashing. This is also a deliberate **clean-room reimplementation** — the
private hardware helper that inspired the project used hand-rolled `wmic`/
`/proc` parsing; we did not copy it.

## ADR-002 — Self-registering collectors + uniform Section

**Context.** Hardware coverage will grow; we don't want each new probe to ripple
through the CLI and every renderer.
**Decision.** Every collector returns a uniform `Section`; collectors
self-register via `@register`; renderers walk sections generically.
**Consequences.** Adding a collector is one new module — zero changes in `core`,
`report`, or `cli`. The cost is an import-for-side-effect in
`collectors/__init__.py`, which is explicit and listed.

## ADR-003 — Isolate each collector; never abort the scan

**Context.** A single flaky probe (e.g. `nvidia-smi` hanging, a permission
error) could otherwise sink the entire inventory.
**Decision.** Run each collector inside `try/except`; on failure emit an `ERROR`
section with the traceback and continue.
**Consequences.** Partial results are always available — the most useful
behavior for a diagnostic tool run on an unknown machine. Bugs are visible (as
`error` sections) rather than silent.

## ADR-004 — Explicit status enum over booleans / missing keys

**Context.** "No GPU", "not implemented on this OS", "psutil missing", and "it
crashed" are different things and a reader needs to tell them apart.
**Decision.** A `Status` enum: `ok / partial / unavailable / unsupported /
error`, inheriting `str` for clean JSON.
**Consequences.** Honest output (a GPU-less box is `unavailable`, not a
failure); the roadmap is visible in the data (`peripherals` = `unsupported`).

## ADR-005 — src-layout package + console script

**Context.** Public repo that should be `pip install`-able and also runnable
straight from a checkout.
**Decision.** `src/` layout, `pyproject.toml` with a `machine-scanner` console
script and `pytest` `pythonpath = ["src"]`.
**Consequences.** Tests run against the installed import path (no accidental
"works only from repo root"); `python -m machine_scanner` and the installed
command both work. Slightly more setup than a flat layout — worth it for a
showcase.

## ADR-006 — Local single-host inventory only (scope guard)

**Context.** "Scan the network" could mean inventorying *this* machine's
interfaces, or actively probing *other* hosts.
**Decision.** Inventory **this machine only**. No port scanning of other hosts,
no remote/fleet mode.
**Consequences.** The tool stays unambiguously a benign diagnostic utility,
which matters for a public portfolio piece. Fleet aggregation, if ever wanted,
would be a separate project consuming the JSON output.

## ADR-007 — Fully recursive text renderer

**Context.** Collector data is arbitrarily nested (a network interface holds a
list of address dicts; that is a list-inside-a-dict-inside-a-list). The first
text renderer only descended one level, so nested lists printed as a raw Python
`repr` — unreadable, while JSON/HTML were fine.
**Decision.** Make the text renderer fully recursive (`_render_value` /
`_render_mapping`) to any depth: dicts print as `key: value`, lists of records
are separated by blank lines, empty lists print `(none)`. `str`/`bytes` are
explicitly treated as scalars (they are `Sequence`s) so a string never explodes
into one line per character.
**Consequences.** The text report is now the equal of JSON/HTML for nested data
with no per-collector formatting code. Renderer stays generic — new collectors
inherit readable output for free.

## ADR-008 — Exit codes distinguish bugs from expected gaps

**Context.** A script wrapping the tool needs to know whether a scan actually
*failed* versus simply found nothing (no GPU, no swap, psutil absent).
**Decision.** Exit `0` on a clean run; exit `2` only when at least one section
is `ERROR` (a collector raised — a genuine bug). `partial` / `unavailable` /
`unsupported` are expected outcomes and keep exit `0`.
**Consequences.** CI and shell callers get a meaningful signal that mirrors the
`Status` enum (ADR-004) without parsing output. Expected hardware gaps never
trip an automated check.

## ADR-009 — Firmware identity: CIM (not `wmic`) on Windows, sysfs (not `dmidecode`) on Linux

**Context.** The first "deeper than psutil" collector (`baseboard`: motherboard
/ BIOS / serials, read from the SMBIOS/DMI tables) needs a per-OS source. The
obvious textbook commands are `wmic` on Windows and `dmidecode` on Linux, but
both are poor choices today: `wmic` is **deprecated and absent from recent
Windows builds**, and `dmidecode` needs **root** (it reads `/dev/mem`) and is
not always installed.
**Decision.**
- **Windows** — query `Win32_BIOS` / `Win32_BaseBoard` /
  `Win32_ComputerSystemProduct` through **PowerShell CIM** (`Get-CimInstance …
  | ConvertTo-Json`), parsed as JSON. A single PowerShell pass with a 20 s
  budget (start-up + three CIM queries can exceed the default 5 s).
- **Linux** — read the kernel-exported DMI table files under
  **`/sys/class/dmi/id/`** directly. The identity fields are world-readable with
  no binary dependency; only the `*_serial` / `*_uuid` files are root-only
  (mode 0400), so a `PermissionError` there is the *precise* elevation signal.
- **macOS** — `system_profiler SPHardwareDataType` via `run_command`.
- **other** — `UNSUPPORTED`.
SMBIOS placeholder junk ("To Be Filled By O.E.M.", "Default string",
all-`F` UUIDs, …) is scrubbed to `None` so a blank field reads as genuinely
unknown. The elevation note fires only when **no** serial/UUID at all is
readable while unprivileged (a systematic block) — a single empty board-serial
is just unpopulated firmware, not a permission problem.
**Consequences.** Works unprivileged for the common case on both major OSes,
with an honest, *accurate* "run elevated for serials" note when (and only when)
elevation would actually help. No dependency on deprecated/absent binaries.
The Linux path is plain file I/O rather than `run_command`; that is a
deliberate exception to the "probe via `run_command`" convention because sysfs
is strictly better here (no root, no subprocess, no locale parsing) — the
Windows and macOS paths still go through the guarded `run_command`. Verified on
Windows (live Lenovo SMBIOS read) and via a WSL2 smoke run (no DMI table there →
clean `UNAVAILABLE`).
