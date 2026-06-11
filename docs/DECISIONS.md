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

## ADR-010 — Multi-vendor GPU + physical RAM modules: enumerate generically, enrich NVIDIA, accept root where it's the only door

**Context.** Closing F2 needs two more deep collectors: GPU **beyond NVIDIA**
(AMD / Intel / integrated) and the **physical RAM modules** (per-DIMM). The
existing `gpu` collector only knew `nvidia-smi`. Picking sources reopens the
ADR-009 question — but the answer isn't the same for every probe.
**Decision.**
- **GPU — two layers.** A *generic enumerator* lists every adapter per OS
  (`Win32_VideoController` CIM on Windows; `lspci` on Linux, falling back to
  `/sys/class/drm/*/device/vendor` PCI IDs when `pciutils` is absent;
  `system_profiler SPDisplaysDataType` on macOS). `nvidia-smi` stays as an
  *enrichment* layer: NVIDIA cards are reported from `nvidia-smi` (live VRAM /
  temp / driver) and everything else from the generic enumerator, so the richer
  source wins for NVIDIA without losing the others. Here `lspci` **earns** its
  use over sysfs (unlike ADR-009) because it resolves human adapter *names* that
  raw PCI IDs can't — the sysfs path is only a degraded, names-less fallback.
- **RAM modules — root is the only door on Linux.** Windows uses
  `Win32_PhysicalMemory` (CIM); macOS uses `system_profiler SPMemoryDataType`.
  Linux uses **`dmidecode -t memory`** — and here, *unlike* `baseboard`, there
  is **no unprivileged sysfs equivalent** for SMBIOS type 17, so the collector
  legitimately needs root and degrades to `UNAVAILABLE` with a "run as root"
  note when it can't read it. The ADR-009 "prefer sysfs" rule is a *preference
  where sysfs exists*, not a ban on `dmidecode` when it's the only option.
- A shared `collectors/_smbios.py` helper (sibling of `_psutil.py`) centralizes
  the PowerShell-CIM-to-JSON call (normalizing PowerShell's single-object vs
  array output to a list) and the SMBIOS placeholder scrub.
**Consequences.** `gpu` now reports AMD/Intel/iGPU, not just NVIDIA; the showcase
no longer shows a half-done collector. The two probes show the *judgement* in
ADR-009 rather than a dogma: choose sysfs when it's strictly better (`baseboard`),
`lspci` when it adds names (`gpu`), `dmidecode`+root when nothing else exists
(`memory_modules`). Verified live on Windows (Intel iGPU; 2×4 GB DDR3-1600) and
via WSL2 smoke (no `lspci`/`dmidecode` → clean `UNAVAILABLE` with accurate notes).

## ADR-011 — Peripherals (USB): VID:PID as the cross-OS identity, a flat list, hubs kept

**Context.** F3 opens the `peripherals` stub. USB is the first category, and it
raises three choices that aren't obvious: which source per OS, what the *record*
should look like across very different outputs, and whether to model the USB
*tree* (host controller → hub → device) or flatten it.
**Decision.**
- **Source per OS** (same judgement as ADR-009/010, not a dogma):
  - **Windows** — `Win32_PnPEntity` via CIM, filtered to rows whose
    `PNPDeviceID` is under the `USB` enumerator. (`Get-PnpDevice` would also
    work but isn't a CIM class; staying on `Get-CimInstance` reuses
    `_smbios.run_cim` and its JSON normalization.)
  - **Linux** — `lsusb` first (it resolves vendor/device *names* from the USB
    ID database that bare IDs can't), with a **`/sys/bus/usb/devices` fallback**
    when `usbutils` is absent — a degraded, names-poorer path. This is the exact
    `lspci`-vs-sysfs trade-off from ADR-010's GPU enumerator.
  - **macOS** — `system_profiler SPUSBDataType`.
- **Normalized record = `{name, vendor_id, product_id, manufacturer}` with the
  16-bit VID:PID pair (lower-case hex) as the stable identity.** Every source
  exposes VID/PID (Windows in the `PNPDeviceID`, Linux as `idVendor`/`idProduct`
  or the `ID xxxx:yyyy` column, macOS as `Vendor ID`/`Product ID`), so it is the
  one field that means the same thing everywhere and lets a reader cross-ref a
  device regardless of the OS it was scanned on.
- **Flat list, not the hub tree.** USB is physically a tree, but for an
  *inventory* the tree adds nesting without adding inventory value; a flat list
  of every node keyed by VID:PID is simpler to read and to diff (F4). **Hubs and
  root hubs are kept, not filtered** — deciding which devices are "real
  peripherals" vs "internal plumbing" is guesswork that risks dropping genuine
  devices; honest over-inclusion beats a lossy heuristic. (macOS is the one
  exception: its bus/controller *headers* carry no VID/PID at all, so they fall
  out naturally — a node with neither ID is dropped.)
- **No elevation needed** on any OS for USB enumeration, so — unlike `baseboard`
  / `memory_modules` — there is no privilege note.
**Consequences.** The `peripherals` section now shows real data instead of a
roadmap placeholder. Verified live on Windows (Logitech receiver, a SanDisk mass
-storage stick, Intel hubs — all with VID:PID) and via WSL2 smoke (no `lsusb`,
no `/sys/bus/usb` → clean `UNAVAILABLE` with an accurate note, no crash). USB is
the only category implemented this phase; monitors / battery / input devices are
left as straightforward follow-ups using the same dispatch shape.
