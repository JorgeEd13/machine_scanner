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
*Superseded in part by ADR-012:* the "one `peripherals` section, add a key per
category" idea floated here was reversed — each category is now its own section.

## ADR-012 — Peripherals are separate sibling collectors, not one grouped section

**Context.** F3's first cut shipped USB inside a single `peripherals` section
and noted that later categories (monitors, battery, input, audio) would "add a
key" to it. Implementing the full set forced the question: one grouped section
with nested category keys, or one collector/section per category?
**Decision.** **One collector per category, each its own top-level `Section`** —
`usb`, `monitors`, `battery`, `input`, `audio` — siblings of `cpu` / `gpu` /
`baseboard`. The just-shipped `peripherals` section is **renamed to `usb`** (its
data key `usb` → `devices`) for consistency; `peripherals` was a ROADMAP *bucket*
name, never a hardware topic. This reverses the "add a key" note in ADR-011.
Rationale, straight from the project's own ADRs:
- **Honest per-category status (ADR-004).** `Status` is per-`Section` and means
  something different per category: a laptop reports `battery=ok` while
  `usb=ok`; a desktop reports `battery=unavailable` (no battery) while
  `monitors=ok`. One grouped section would have to collapse those into a single
  status and re-encode the real state inside `data`.
- **Isolation for free (ADR-003).** The registry already runs each collector in
  its own `try/except` — five separate collectors means one probe hanging or
  raising can't sink the other four. A grouped collector would have to
  re-implement that per-category guard by hand.
- **One module per topic (ADR-002).** Adding a topic is already "one new module,
  zero changes elsewhere"; monitors/battery/audio *are* distinct topics with
  distinct sources, so they fit the established growth pattern exactly.
**Consequences.** The report grows by four sibling sections instead of nesting,
which the generic renderers (ADR-002/007) handle with zero changes. The JSON
schema's section names are now stable single-topic keys (good for the F4 diff,
which keys on them). Cost: the `peripherals` → `usb` rename churns the section
name shipped earlier the same day — accepted, since the schema is easier to get
right now than after F4 consumes it. Net for F3: `usb` (ADR-011) + `monitors`
(EDID), `battery`, `input`, `audio`; Bluetooth and printers remain queued as
further siblings.

## ADR-013 — Physical storage: MSFT_PhysicalDisk over Win32_DiskDrive; SMART is best-effort/elevated

**Context.** The `disk` collector reports psutil partitions/usage only — not the
*physical* drives behind them. F2.x adds a `storage_devices` sibling (one
collector = one section, ADR-012) for drive model / serial / firmware / size /
**bus type** (NVMe/SATA/USB) / **media type** (SSD/HDD) / **SMART health**. As
with ADR-009/010, the per-OS source is a judgement call, and two choices were
non-obvious: which Windows class to spine on, and how far to push SMART.
**Decision.**
- **Windows — `MSFT_PhysicalDisk` (`root\microsoft\windows\storage`) is the
  spine, not `Win32_DiskDrive`.** Only `MSFT_PhysicalDisk` exposes `MediaType`
  (SSD vs HDD) and `BusType` (NVMe/SATA/USB) as clean enums *plus* a
  storage-stack `HealthStatus` — and it does so **without elevation**.
  `Win32_DiskDrive` has no media type at all and only a coarse `InterfaceType`
  (IDE/SCSI/USB — it reports NVMe drives as "SCSI"), so it is kept strictly as a
  **fallback** for older Windows lacking the storage WMI provider
  (model/serial/firmware/size, coarse bus, no media, with a note).
- **SMART predictive-failure is best-effort and elevation-gated.** The raw bit
  lives in `MSStorageDriver_FailurePredictStatus` (`root\wmi`) which typically
  needs administrator. Its `InstanceName` is a SCSI port path that does **not**
  carry the disk number, so per-drive correlation would be guesswork — we
  therefore reduce it to a single fleet-wide "is *any* drive predicting failure"
  signal surfaced as a section note, and rely on `MSFT_PhysicalDisk.HealthStatus`
  for the per-drive `health`. When the query is blocked (None) and we are not
  admin, the section degrades to **PARTIAL + an elevation note** (the
  baseboard / memory_modules root-gating pattern). An empty-but-readable result
  is *not* treated as "all healthy" (returns None, no claim) — honest over
  convenient. Verified live: this desktop read both drives' identity and
  `health: healthy` unprivileged; the predictive query returned empty without
  admin, so it correctly did **not** gate to PARTIAL.
- **Linux — `lsblk -d -b -O -J` (parse the JSON, not columns).** It resolves
  model / serial / firmware (`rev`) / size (bytes via `-b`) / `rota` (HDD vs SSD)
  / `tran` (bus) in one no-root call. `/sys/block/*` is the **fallback** when
  `lsblk` is absent — bus-poor there (only the `nvme` naming is unambiguous
  without `lspci`), so it carries a note. SMART via `smartctl -H -j` needs root;
  unreadable → degrade with a note (and PARTIAL when privilege is the cause).
- **macOS — `diskutil info -all`**, keeping only `Virtual: No` blocks
  (media name / size / `Protocol` bus / `Solid State` flag / `SMART Status`).
- **other — `UNSUPPORTED`.**
- **`disk` is left untouched** — it stays the psutil partitions/usage view;
  `storage_devices` is the deep-hardware layer beside it, not a replacement.
**Consequences.** The deep-hardware gap `disk` left is closed without a new
dependency. Bus/media type are honest enums on Windows and Linux; SMART is
reported where it is genuinely readable and degrades to an accurate elevation
note where it isn't, never to a false health claim. Verified live on Windows
(ADATA SATA SSD + SanDisk USB, both with bus/media/health) and via WSL2 (4
Hyper-V virtual disks through the lsblk-JSON path → PARTIAL with the
smartctl/root note, zero ERROR, exit 0). The `lsblk` JSON parse, the sysfs
fallback, the SMART gate and the diskutil parser are all covered by offline
tests (canned JSON, a tmp `/sys/block` tree, stubbed `run_cim`/`run_command`).

## ADR-014 — Bluetooth: report adapters *and* paired devices as separate levels; `bluetoothctl` over sysfs for names

**Context.** The first F3-extras collector (`bluetooth`) reopens the per-OS
source question (ADR-009/010/011) plus one that is specific to Bluetooth: it has
two genuinely different inventory levels — the local **radio/adapter** and the
**paired/known remote devices** — and the per-OS sources expose them
asymmetrically. Reporting only one level would be a lossy half-answer (an adapter
with no paired list, or a device list with no proof of a radio).
**Decision.**
- **Keep both levels, in separate keys.** The section data is
  `{"adapters": [...], "devices": [...]}` (+ counts), never a single flat blob.
  A box with a radio but zero paired devices is still `ok` (adapters non-empty);
  only *neither* degrades to `unavailable`. This mirrors the ADR-012 "honest
  per-category status" reasoning one level deeper — adapter-present and
  device-present are distinct facts a reader needs to tell apart.
- **Source per OS** (same judgement as ADR-011, not a dogma):
  - **Windows** — `Win32_PnPEntity` filtered to `PNPClass='Bluetooth'` via CIM
    (the `usb` enumerator-filter shape, reusing `_smbios.run_cim`), wrapped in
    `@()` so a radio-less box emits `[]` (clean "no Bluetooth-class devices")
    rather than nothing (a query failure → `None`) — the `battery` `@()` trick.
    Rows are split by `PNPDeviceID`: a remote/paired device carries
    `DEV_<12-hex-mac>` (→ `devices`, MAC formatted `aa:bb:..`); a
    `BTHENUM\{guid}_…` service/profile sub-node with no `DEV_` is noise (dropped);
    anything else is the local radio (→ `adapters`).
  - **Linux — `bluetoothctl devices` for the device level, `/sys/class/bluetooth`
    for the adapter level.** `bluetoothctl` *earns* its use over sysfs (unlike
    `baseboard`'s sysfs preference in ADR-009) for the same reason `lsusb`/`lspci`
    do in ADR-010/011: it resolves remote **device names** that the kernel's
    `/sys/class/bluetooth` (which only enumerates `hciX` adapters, not peers)
    cannot. The two are *complementary, not fallbacks of each other*: adapters
    always come from sysfs (no daemon needed), the paired list from
    `bluetoothctl`. When `bluetoothctl` is absent or no controller is up
    (`run_command` → `None`), the adapters still report from sysfs with an
    explicit "no paired-device list" note; when sysfs has no `hciX` **and**
    `bluetoothctl` yields nothing, the section is a clean `unavailable` (no radio
    or no BT service) — never an error (ADR-003/004/008).
  - **macOS** — `system_profiler SPBluetoothDataType` (a nested
    `Bluetooth Controller:` block → adapter, plus `Connected:` / `Not Connected:`
    device groups → devices).
  - **other** — `unsupported`.
**Consequences.** Bluetooth reports the radio and the paired peripherals as the
two distinct things they are, on every OS, without a new dependency. Verified
live on Windows (this desktop has no radio → clean `unavailable`, correctly *not*
an error) and via WSL2 (no `/sys/class/bluetooth`, no `bluetoothctl` → clean
`unavailable`, zero ERROR). The Windows BTHENUM classification, the
`bluetoothctl` parse, the sysfs-adapter path and the macOS nested parse are all
covered by offline tests (canned CIM rows, a tmp `hciX` tree, canned
`bluetoothctl`/`system_profiler` text). *Printers*, shipped in the same phase,
needed **no** ADR — `Win32_Printer` / `lpstat -p`+`-d` (CUPS) / `SPPrintersDataType`
is the straightforward ADR-011 dispatch shape with no non-obvious choice.

## ADR-015 — Interactive HTML = inline vanilla JS, no framework, no external assets

**Context.** F4 turns the static HTML report into a genuinely shareable,
*interactive* artifact: collapsible sections, a search/filter box, and
copy-as-JSON (per section and whole-scan). Interactivity forces a real choice
that the static renderer never faced — **how** to add behaviour to a file that
must stay a single, portable, drop-on-a-USB-stick document. The options were:
(a) a JS framework / bundler (React, Alpine, …), (b) a CDN-hosted library, or
(c) hand-written vanilla JS inlined into the page.
**Decision.** **Option (c): inline vanilla JS + inline CSS, zero external
assets.** No framework, no bundler, no CDN, no external `src`/`href`. The whole
report remains one self-contained `.html` file. Concretely:
- **Collapse is native `<details>`/`<summary>`**, not JS-driven. This is the
  load-bearing choice: with JavaScript disabled the document still *fully works*
  as a readable static report — every section is laid out as a tree and
  collapses natively; only the search box and copy buttons go inert. The
  interactive layer is **progressive enhancement**, never a hard dependency.
- **Search** filters `<details>` cards by a precomputed lowercase `data-search`
  haystack (section name + every key/value + notes); **copy** reads an
  HTML-escaped JSON payload from a `data-copy-json` attribute and writes it via
  `navigator.clipboard` with a `<textarea>+execCommand` fallback for non-secure
  contexts. JSON lives in attributes (decoded losslessly by `getAttribute`)
  rather than `<script>` tags, sidestepping any `</script>`-in-data escaping
  hazard.
- **Nested data is rendered as a recursive HTML tree** (`_render_value` /
  `_render_mapping`) — the structural twin of the text renderer's ADR-007 — not
  a raw `<pre>` JSON dump. `<pre>` is kept only as a leaf fallback for a value
  that is somehow neither mapping, list nor scalar; it is never used to dump a
  whole structure.
**Consequences.** The report stays a single portable file with **no new
dependency** (keeps CI and the F5 binary story clean) and works offline forever
— no CDN to rot, nothing to fetch. Choosing native `<details>` over a JS
accordion means the no-JS degradation is honest rather than a blank page. The
cost is hand-written DOM code instead of a framework's conveniences, which at
this scope (one search box, a few buttons, ~40 lines of JS) is trivial. The diff
renderer (`report/diff.py`'s `diff_to_html`) follows the same rule: self-contained,
inline CSS, no JS needed at all. A focused offline test (`test_html_report.py`)
asserts self-containment (no remote `http(s)`/`src=`/`href=`), the presence of
the search/collapse/copy scaffolding, and that nested data renders as a tree
rather than a `<pre>` blob. Verified live on Windows (a real 16-section scan →
0 external references, 16 native-collapsible cards, copy + search wired, 0 `<pre>`
dumps) and via WSL2 (same, plus the diff renderer self-contained), zero ERROR.

*Diffing itself (`diff_scans`)* needed no separate ADR for its mechanics, but
two of its choices are worth recording here: it is a **pure, renderer-agnostic
compute** (preserving the ADR-002 separation — the diff computes a structure,
the text/HTML renderers only display it, neither crosses over) and it consumes
**two saved JSON scans, never a live re-scan**, so a diff is reproducible and
offline. Within a section it keys changes on a **deterministic index-based path**
(`data.devices[2].vid`): a reordered list shows as field changes rather than a
move — an accepted, honest trade-off for an inventory diff, where determinism of
the path matters more than order-invariance.
