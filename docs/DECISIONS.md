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

> **Addendum (2026-07-20, ADR-021):** the manifest moved out of
> `collectors/__init__.py` into `collectors/_all.py`. The mechanism is unchanged
> — collectors still self-register on import, and the list is still explicit —
> but the package `__init__` no longer imports anything, so importing one
> collector no longer imports all of them. That is what lets the requirements
> checker ship a build containing five.

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

*Favicon addendum (2026-06-12).* The report now carries the project's brand
hypercube as a **favicon inlined as a `data:image/png;base64,…` URI** in `<head>`.
A `data:` URI is **not** an external fetch — it travels inside the single file —
so it keeps the ADR-015 self-containment promise intact. The self-containment
test was refined accordingly: it no longer bans `src=`/`href=` outright (a blunt
proxy) but asserts every `src`/`href` value **starts with `data:`** (plus the
existing `http(s)` ban). The favicon PNG is derived from the project logo; if a
future asset is added it must likewise be a `data:` URI or the test fails.

*Diffing itself (`diff_scans`)* needed no separate ADR for its mechanics, but
two of its choices are worth recording here: it is a **pure, renderer-agnostic
compute** (preserving the ADR-002 separation — the diff computes a structure,
the text/HTML renderers only display it, neither crosses over) and it consumes
**two saved JSON scans, never a live re-scan**, so a diff is reproducible and
offline. Within a section it keys changes on a **deterministic index-based path**
(`data.devices[2].vid`): a reordered list shows as field changes rather than a
move — an accepted, honest trade-off for an inventory diff, where determinism of
the path matters more than order-invariance.

## ADR-016 — Force UTF-8 end-to-end for subprocess output (the OEM-vs-ANSI mojibake bug)

**Context.** On a pt-BR Windows box the captured data — not just the console —
came back corrupted: a keyboard named `Aperfeiçoado` arrived as `Aperfei‡oado`
and `padrão` as `padrÆo`, and that mojibake was written straight into the JSON
artifact. Root cause: **two different Windows code pages**. Windows PowerShell
5.1 writes its stdout in the console **OEM** code page (cp850 on pt-BR), but
`run_command` used `subprocess` with `text=True` and no explicit encoding, so
Python decoded with the **locale ANSI** code page (cp1252). cp850 and cp1252
disagree on the high bytes, so the decode *silently succeeded with the wrong
characters* (`ç` = cp850 `0x87` → cp1252 `‡`; `ã` = cp850 `0xC6` → cp1252 `Æ`) —
`errors="replace"` never fired because nothing was undecodable, just mis-mapped.
An earlier STATE note mis-diagnosed this as a *text-renderer* console-codepage
cosmetic issue and claimed "the JSON is correct"; it was not.
**Decision.** **Make UTF-8 the single encoding on both ends.**
- `core.platform.run_command` decodes subprocess output as **`encoding="utf-8",
  errors="replace"`** instead of the locale default. Linux/macOS tools already
  emit UTF-8, so this is correct there; the only Windows non-PowerShell caller is
  `nvidia-smi` (ASCII), so it is safe too.
- Every PowerShell invocation is prefixed with **`POWERSHELL_UTF8`** =
  `"[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "`,
  forcing PowerShell to *emit* UTF-8 to match. A **no-BOM** `UTF8Encoding` is
  used so the JSON has no leading BOM; `run_cim` still strips a BOM defensively
  (`_strip_bom`, via a `utf-8-sig` round-trip — no invisible BOM character in the
  source). Both `_smbios.run_cim` (10 collectors) and `baseboard`'s direct
  PowerShell call get the prefix.
**Consequences.** Accented device / manufacturer names are now captured
correctly across locales, so the JSON archive and every renderer are right — not
just the console. The fix is centralized (one constant + one decode change),
adds no dependency, and is locked by offline tests (`test_platform_encoding.py`:
`run_command` passes `encoding="utf-8"`; `run_cim` prepends the prefix and
strips a BOM; the accented round-trip survives). Verified live on Windows
(`input` → `Aperfeiçoado`, `padrão`; no `‡`/`Æ` bytes in the JSON). The general
rule this sets: **never rely on the platform default code page for subprocess
text — pin UTF-8 and make the child emit it too.**

## ADR-017 — Frozen no-args writes+opens an HTML report; default filename localized by OS language

**Context.** F5 ships the tool as a double-clickable binary. A double-clicked
console app that scans, prints text to stdout and exits just **flashes a console
window and closes** — the user sees nothing. The packaged binary needs a useful
default action when launched with no arguments, *without* changing the script's
long-standing CLI default (text to stdout — every test and the README rely on
it). Separately, a bare `machine_inventory.html` reads oddly on a non-English
desktop; a localized *filename* is a cheap, honest touch.
**Decision.**
- **A `--report` one-shot mode**: scan → write a self-contained HTML report to a
  file → open it with `webbrowser`. Browser-open is best-effort (a headless box
  still gets the file; `webbrowser.open` failures are swallowed). The run still
  returns exit 2 if any collector errored (ADR-008 preserved).
- **Gate the implicit trigger on `sys.frozen` *and* no args.** Report mode fires
  automatically only when `getattr(sys, "frozen", False)` is true **and** there
  were no CLI arguments — i.e. a double-clicked binary. A frozen binary run
  *with* args (`machine-scanner-windows.exe --json` in a terminal) and the
  unfrozen script with no args both keep the original text-to-stdout default. So
  the new behavior is scoped exactly to the double-click case and the explicit
  `--report` flag; nothing else changes.
- **Localized default *filename* only, via a tiny hardcoded language→name map**
  (`report_name.py`): `en → machine_inventory`, `pt → inventario_de_maquina`,
  `es → inventario_de_equipo`, `fr → inventaire_machine`, `de → maschineninventar`,
  English fallback for anything else. The language is detected best-effort and
  pure-stdlib: Windows `GetUserDefaultUILanguage` → `locale.windows_locale` LCID
  map, else the POSIX `LC_ALL`/`LANG`/`LANGUAGE` env family, else
  `locale.getlocale`/`getdefaultlocale`, else `en`. Detection never raises (any
  failure falls through to English). `-o` overrides the name entirely.
- **Filename only — report *content* stays English.** Full content i18n
  (section labels, values) conflicts with the project's "English everywhere"
  rule and is a genuinely larger effort; it stays parked under ROADMAP Ideas.
  This ADR translates exactly one string: the default filename.
**Consequences.** Double-clicking the binary now leaves a viewable artifact and
opens it, instead of a blink-and-gone console — the single biggest UX gap for a
non-technical reviewer running the stick. The `sys.frozen`+no-args gate keeps
the change invisible to the CLI/test surface (the existing 227 tests are
untouched; 12 new offline tests pin the map, the detection-never-raises
contract, and the four routing cases: `--report`, frozen-no-args, frozen-with-
args, unfrozen-no-args). Verified live: the Windows binary double-clicked on this
pt-BR box wrote **`inventario_de_maquina.html`** (localized) and opened it,
exit 0. Trade-off: language detection is best-effort and territory-blind (`pt_BR`
and `pt_PT` both → `pt`), which is fine for a filename.

## ADR-018 — One-file binaries; collectors found via the import graph; unsigned, documented

**Context.** F5's packaging raised three non-obvious choices: **one-file vs
one-folder** PyInstaller output, **how the frozen app finds its collectors**
(the self-registration in ADR-002 depends on import side-effects that a static
bundler might miss), and **code signing**.
**Decision.**
- **One-file (`--onefile`-equivalent single `EXE`), not one-folder.** The whole
  project promise is "drop one thing on a stick and run it anywhere" (the same
  spirit as ADR-015's zero-external-asset HTML report). A one-folder build is a
  directory of dozens of DLLs/`.so`s that must travel together; one self-
  contained executable per OS is the honest match to the pitch. The accepted
  cost is a **first-run temp-extraction delay** (the bootloader unpacks to a
  temp dir): measured ~15 s cold (extraction + Defender scanning a fresh unsigned
  exe) and ~3 s warm on this box. For an inventory tool run occasionally, not a
  hot path, that trade is right.
- **Collectors are found by the import graph, reinforced by explicit
  `hiddenimports`.** ADR-002's self-registration works *because*
  `collectors/__init__.py` imports each collector module explicitly, so
  PyInstaller's static analysis follows those edges and bundles all 16. To make
  that guarantee independent of analysis heuristics, the spec **also** lists the
  16 modules in `hiddenimports` — belt-and-suspenders. The frozen `--list` is
  asserted to return 16 both in local verification and in the release workflow's
  per-OS smoke test, so a dropped collector fails the build rather than shipping
  silently. Verified live: the Windows binary's `--list` shows all 16.
- **Ship unsigned, document it.** Code-signing needs a paid certificate
  (Windows) / an Apple Developer ID; for a free, open-source portfolio tool that
  cost isn't justified. The binaries are therefore unsigned and SmartScreen /
  Gatekeeper may warn on first run. This is stated plainly in `build/README.md`
  rather than hidden — the source and the exact build workflow are in the repo,
  which is the honest substitute for a signature.
**Consequences.** A single downloadable file per OS that runs with no Python
installed (the F5 DoD). The entry point is a thin `build/entrypoint.py` doing an
absolute `from machine_scanner.cli import main` (a PyInstaller entry runs as
`__main__`, so the package's relative-import `__main__.py` can't be the target).
`pyinstaller` is a build-time-only `[build]` extra, never a runtime dep / in
`requirements.txt` (ADR-001 holds). macOS and Linux binaries are produced by the
release runners — they can't be built on this Windows box, and WSL here has no
`pip`; that division of labor is explicit, not hand-waved.

---

## ADR-019 — Model fit is an **advisor**, not a collector: derived from the scan, never re-probed

**Date:** 2026-07-20 · **Status:** accepted

**Context.** The tool needed to answer "which local LLM can this machine run?"
— the natural next question after "what is this machine?", and already implied
by the README's *"sizing a machine for a workload"* framing.

The obvious implementation is a 17th collector. It is the wrong one.

**The problem with a collector.** A collector is a **zero-arg callable that
cannot see its siblings** (`core/registry.py`) — that isolation is what keeps a
flaky probe from costing you the rest of the scan. But model selection is a
question about **CPU, memory, GPU and disk at once**. A collector could only
answer it by **re-detecting all four itself**, which means a second, divergent
copy of the detection logic living beside the one that already works — and the
GPU probe in particular is the most OS-specific code in the repo (ADR-010).

**Decision.** A new layer, `advisor/`: pure functions that take a completed
`Inventory` and return a derived `Section`. It probes nothing. `cli.py` appends
it after `run_all()`, the way it already wires registry → renderer.

**Why this is the same split the repo already makes.** `report/diff.py` computes
over saved scans and its formatters display without recomputing (ADR-015). The
advisor is that boundary applied one step earlier: **collect once, derive many
times.** Layering stays acyclic — `advisor/` depends on `core.models` only,
never on collectors, never on `report`.

**Consequences.**
- **Tests are hardware-agnostic by construction.** Every branch of the heuristic
  is reachable from a synthetic `Inventory` dict — including hardware nobody
  here owns (a 70B-capable workstation, a saturated Windows VRAM reading).
- **`--only` needs a rule.** The advisor is not in `--list` (it is not a
  collector) but `--only ollama_fit` works and `--only cpu` correctly omits it.
- **It is only as good as the scan.** A section it needs being `UNAVAILABLE`
  makes the advice `UNAVAILABLE` too, with the reason. It never guesses.

**Rejected — probing Ollama itself.** Asking `/api/tags` which models are
already pulled would sharpen the recommendation. But the question this answers
is asked *before* anything is installed, on a machine where Ollama's absence is
the normal case. Adding a network call would make a pure function impure to
improve an answer for users who need it least. A future readiness check — "is
the prerequisite actually installed and working" — is a **different question at
a different moment**, and belongs in its own mode.

---

## ADR-020 — The catalog is ported from `receivables-agent`, and that is not a clean-room breach

**Date:** 2026-07-20 · **Status:** accepted

**Context.** Golden rule 2 of `CLAUDE.md` says clean room, and names a **private**
`hardware.py` as explicitly not a source to copy from. The model catalog and the
effective-memory heuristic in `advisor/` come from a `hardware.py` — the one in
`receivables-agent`.

**Decision.** The port is allowed and recorded here so a future session does not
read it as a violation and "fix" it.

**Why they are different cases.** The rule protects against carrying in code or
data from **private, third-party-owned** work. `receivables-agent` is the same
author's **public, MIT-licensed** repo. There is nothing confidential in a list
of public Ollama tags and a "reserve 20% of RAM" rule of thumb.

**What was actually reused, honestly.** The *catalog numbers* and the
*effective-memory idea*. Nothing else survived the move, because the two tools
run at opposite moments:

| | `receivables-agent` `hardware.py` | `advisor/` |
|---|---|---|
| runs | inside the app, at construction | standalone, before anything is installed |
| detection | its own psutil/`nvidia-smi` probes | none — reads a completed scan |
| GPU vendors | NVIDIA only | whatever the `gpu` collector enumerated |
| integrated GPUs | not considered | excluded, or the sizing double-counts RAM |
| disk | ignored | part of the verdict |
| output | an `OLLAMA_MODEL=` line for a container | a verdict a person reads |

**The rule this leaves behind.** Reuse of one's own public engineering is fine
and should be recorded, not hidden. Carrying content out of private or
client-owned work is the thing the rule exists to stop, and it is untouched.

---

## ADR-021 — The requirements checker is a SECOND binary that bundles only the collectors it uses

**Date:** 2026-07-20 · **Status:** accepted

**Context.** ADR-019's advisor answers "which model fits?" inside a full scan.
But the person who most needs that answer is a stranger who was *sent* a binary
and has no reason to trust it yet — and handing them a full inventory means
handing back hostname, username, IP and MAC addresses, disk serials, monitor
serials and a list of every USB device. Roughly **13,000 characters, of which
about 4,300 bear on the decision.**

**Decision.** A second entry point (`qualifier.py`) and a second one-file binary
(`ai-model-requirements-{windows.exe,linux,macos}`) that runs **five collectors**
— cpu, memory, gpu, disk, llm_runtime — strips `hostname` and `user` from the
scan metadata, and renders a one-page verdict instead of an inventory.

**Why a separate binary rather than a flag.**

- **The claim has to be about the artifact.** "It cannot read your serial
  numbers" is checkable; "it does not, by default" is a promise about how it was
  invoked. The spec `excludes` the other twelve collector modules, so there is
  no argument that turns this build into an inventory tool.
- **Double-click has to be the entire interaction.** The audience does not
  discover flags.
- **Collecting less is the product, not a limitation.** The buyer for this is
  someone who cannot send their data to a third party. Interaction #1 asking for
  a machine fingerprint contradicts the pitch before it is made.

**The refactor it forced, and why it is an improvement anyway.** A package's
`__init__` runs whenever any submodule is imported, so while
`collectors/__init__.py` held the import-everything manifest, "load one
collector" and "load all seventeen" were the same act — the excludes could not
work. The manifest moved to `collectors/_all.py`; the package now imports
nothing. **The set of collectors became a choice the entry point makes**, which
is what ADR-002's self-registration always implied but could not express. The
registry gained `run_all(autoload=False)` for callers that import their own.

**Smoke-test gotcha (2026-07-20, found on the first Windows run).** The PowerShell
branch checked the verdict with `if ($out -notmatch "...")`. `&` on a native exe
yields a **string array**, and `-match`/`-notmatch` on an array *filters* it
instead of returning a boolean — so the condition was true whenever any single
line failed to match, i.e. always. It failed a working binary. Use
`Select-String -Quiet`, which returns an actual boolean; the Unix branch was
already correct because `grep -q` is one. **The same shape of bug as the
PyInstaller one below: a check that cannot pass and a check that cannot fail are
equally worthless, and both only appear on a real runner.**

**Locked by test.** `test_qualifier_spec_bundles_exactly_the_scope` asserts the
spec's `hiddenimports` equal `qualifier.SCOPE`, that no module is both bundled
and excluded, and that **every** collector module is accounted for as one or the
other. Drift is silent and bad in both directions: a missing module breaks the
check on a client machine, an extra one widens what the binary can read while
the report still claims otherwise.

---

## ADR-022 — Requirement bars are FIXED and published. A machine-derived minimum cannot be failed.

**Date:** 2026-07-20 · **Status:** accepted

**Context.** The natural way to phrase the report is "minimum and recommended for
*your* machine". It does not survive contact with the no-go case.

**The trap.** If the minimum is derived from the machine being measured, **every
machine meets its own minimum by construction** and no machine can ever fail. A
threshold has to come from outside the thing it is measuring.

**Decision.** `catalog.REQUIREMENTS` holds fixed, published bars in the shape a
buyer already knows from **game system requirements** — Minimum and Recommended
columns, your machine checked against each. "What can this machine do?" is
answered separately, by the model-range line.

- **Minimum** = the 3B class: the weakest configuration still worth running.
- **Recommended** = the 7B class: where answers stop being a compromise.

**Three rules the table needs to not lie.**

1. **Memory is one requirement with two routes.** A 6 GB graphics card is enough
   without 16 GB of RAM; 16 GB of RAM is enough with no card at all. Scored
   independently, nearly every machine that actually works would fail. They pass
   together if *either* clears — and when neither does, only RAM is reported as
   the blocker, because saying "you fail on two counts" when adding RAM alone
   fixes it is discouraging and wrong.
2. **The disk bar moves.** It is the only requirement that depends on what is
   already installed: a machine without Ollama and Docker must fit the model
   *and* both installs. The report says *why* the number is not the published
   one. Install sizes are OS-dependent and taken from the **scanned** machine's
   OS, not the one rendering the report.
3. **A soft blocker is not a no.** Failing only on free disk is a ten-minute fix,
   not a purchase — it reads **`NOT YET`**, not `NO`, and the report says what
   the machine would run once the space exists. Collapsing the two loses a
   customer who would qualify by the end of the conversation.

### Amendment (2026-07-20) — three corrections from the first real Windows run

A live 8 GB Windows box read **`NO`**. It should have read `YES, WITH LIMITS`.

1. **A bar in sticker gigabytes cannot be compared against reported gigabytes.**
   A machine never reports the size it was sold as — firmware, integrated
   graphics and reserved regions take a slice first. That box reported **7.9 GB**
   against an **8 GB** minimum; a 16 GB laptop with an Intel iGPU reports as
   little as **14.6** against a 16 GB recommendation. **The bars were rejecting
   exactly the machines they were written to admit.** Fixed with
   `catalog.nominal_ram_gb`, which rounds up to the nearest standard size only
   when the reported figure is within 12% of it — so an unusual configuration is
   never credited with memory it does not have. The reported number stays visible
   in the detail line; only the *comparison* uses the nominal size. **The `fit`
   calculation still uses the reported figure**, because a model runs in real
   memory, not sticker memory.
2. **The conditional sentence contradicted the table.** Under a `NO` the report
   said *"It has the memory for a model — that is not what is blocking it"* two
   lines below a table stating that memory was, in fact, what was blocking it.
   That line was written for the disk case and hardcoded for all of them. It is
   now only emitted when every blocker is soft.
3. **The HTML is pure ASCII.** Non-ASCII characters are emitted as numeric
   entities. This page travels by email, chat upload and USB stick, through tools
   that do not all honour `<meta charset>` — and an em dash read as cp1252 turns
   into `â` (ADR-016's failure mode, in a file this repo hands to strangers). A
   pure-ASCII file cannot be mis-decoded by anything.

**None of these were reachable from a synthetic test that I wrote knowing the
thresholds.** All three needed someone else's actual machine.

**Corollary — a failing machine never gets a recommendation.** "Best available
to you: llama3.1:8b" printed under a `NO` reads as a contradiction. Below the
bar, the phrasing goes conditional: what it *would* run once the blockers clear.

---

## ADR-023 — The recommendation is licence-filtered at the REPORT, and a tiny-model verdict now says why it cannot be trusted. What the 20% headroom means is left open, deliberately.

**Date:** 2026-07-29 · **Status:** accepted (parts 1 and 2); **part 3 OPEN**

### 1. The report threw away a filter `recommend()` had already computed

`advisor/fit.py`'s `recommend()` excludes non-commercial licences from `best`,
carefully, with the reasoning recorded beside it — and `test_advisor_fit.py`
asserted it. **`report/requirements_report.py` then recomputed its own
`best = fitting[-1]`**: the highest-quality model that *fits*, licence ignored.

**Measured:** on a machine whose accelerated ceiling is `qwen2.5:3b` — 4 GB VRAM,
or 4–6 GB RAM on the CPU path — the page headlined *"Best available to you:
qwen2.5:3b"*, a **Qwen Research License** model, to a reader deciding what to run
at work. That is precisely the trap `catalog.py`'s licence fields were added to
prevent, and `qwen2.5:3b` is the model named in that comment as the reason.

**Decision.** `_recommended(rows)` applies the commercial filter; the report's
`best` and its verdict come from it. **The range keeps every fitting model** —
*"this machine can run X"* is a true statement about hardware and hiding it would
make the tool less honest, which is `recommend()`'s own reasoning. When the
headline and the ceiling differ, the page **says why**, rather than letting two
lines quietly disagree.

⚠️ **Why no test caught it:** the licence test existed, in the right file, at the
wrong machine size — 8 GB, where the ceiling is commercial anyway. **A fixture
that cannot reach the defect proves nothing**, and the first draft of the new
test repeated the mistake (a 5 GB CPU box fails the minimum tier, so no model is
ever named and the assertion could not fire). Four tests now, each verified by
mutation.

### 2. A tiny-model recommendation now carries a reliability caution

The `YES, WITH LIMITS` line says *"a smaller and slower one"*. **Speed is not the
problem.** Run end to end against a real document set, `qwen2.5:1.5b` stated that
sabbatical pay came *"through overtime hours rather than in cash"* — citing a
document that says the first four weeks are paid at full salary and contains **no
overtime clause**. Eligibility, duration and return-to-role were correct in the
same answer, which is what makes it dangerous. The same model also ignored an
explicit instruction to answer in a named language.

**Decision.** When the recommendation is at or below `_UNRELIABLE_AT_OR_BELOW`
(quality 2 = `qwen2.5:1.5b` and smaller), the report adds a plain caution: these
answer confidently and wrongly while citing the document, and the size is a
demonstration rather than something to rely on. **Band-specific on purpose** — a
warning printed over every verdict is read on none.

**This does not change what the tool reports as runnable.** The models still fit,
still appear, still get recommended when nothing better does. What changed is the
caution printed over them, which was measurably the wrong caution.

### 3. ⚠️ OPEN — the 20% headroom does not survive contact with a real deployment

`fit.py` reserves 20% of RAM for *"the OS, the desktop and the process holding
the model"*, and on that basis tells an **8 GB** machine its best model is
`qwen2.5:7b`. Measured on a real 8 GB Windows 10 box: Docker Desktop alone cost
**2.15 GB**, two models **2.4 GB**, and the full stack needed **~9.2 GB on a
7.92 GB machine** — it did not refuse, it **paged**.

**Deliberately NOT changed here, and the reason is a boundary worth keeping.**
This tool answers *"what can this machine run?"* — Ollama plus a model, which is
a real and useful question, and 7B on 8 GB is defensible for that. It does **not**
answer *"what can this machine run while also hosting a container stack"*, which
is a different question belonging to whoever is deploying something.

Changing the headroom would alter **public advice for everyone who runs this
tool**, on the basis of one deployment's requirements. That may still be right —
a note distinguishing *"the model alone"* from *"the model plus an application"*
probably is — but it is a decision about this tool's scope, not a bug fix, and it
should be made on purpose rather than as a side effect of a delivery.
