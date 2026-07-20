# CLAUDE.md — conventions for AI-assisted development

Guidance for any AI collaborator (and humans) working in this repo. Read this
first, then [`docs/STATE.md`](docs/STATE.md) for where things currently stand.

## What this project is

`machine_scanner` is a **public portfolio project**: a portable, cross-platform
machine inventory tool (hardware / OS / network) that outputs text, JSON or
HTML. Clean room — it reimplements detection patterns from scratch and contains
no proprietary code or data.

## How to resume (reading order)

1. [`docs/STATE.md`](docs/STATE.md) — current focus, done, next step. **Always.**
2. [`docs/ROADMAP.md`](docs/ROADMAP.md) — phases (F0…F5) with Objective / How / DoD.
3. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the collector/registry/report design.
4. [`docs/DECISIONS.md`](docs/DECISIONS.md) — ADRs (why psutil, why src-layout, …).
5. [`README.md`](README.md) — product-level usage.

## Golden rules

1. **English everywhere.** Names, comments, commits, docs — all English.
2. **Clean room.** Never copy code/data from private projects. The detection
   patterns here are reimplemented from scratch (psutil-based); the private
   `hardware.py` that inspired the idea is *not* a source to copy from.
3. **Secrets hygiene.** Nothing to keep secret here, but never commit a scan of
   a real machine (`.gitignore` covers `scan-*.json` / `*.report.html`).
4. **Plan before you code.** Record non-obvious choices in `docs/DECISIONS.md`.
5. **Token economy.** Volatile state in `docs/STATE.md`; durable design in
   `docs/ARCHITECTURE.md`; decisions in `docs/DECISIONS.md`. Read on demand.

## Architecture in one paragraph

A **collector** is a zero-arg callable that returns a `Section`
(`name`/`title`/`status`/`data`/`notes`). Collectors self-register with
`@register("name")`; the **registry** runs them in isolation (one raising
becomes an `ERROR` section, the scan still completes) into an `Inventory`. The
**report** layer (json/text/html) walks `Inventory.sections` generically and
never imports collectors. **Adding a collector = one new module in
`collectors/` listed in `collectors/_all.py`, the load manifest — zero
changes elsewhere.** (The manifest is not the package `__init__`; ADR-021.)

## Where things live

- `src/machine_scanner/core/`       — `models.py` (Section/Inventory/Status),
  `platform.py` (OS detect, privilege, safe subprocess), `registry.py` (runner)
- `src/machine_scanner/collectors/` — one module per topic (system, cpu, memory,
  disk, network, gpu, peripherals); `_psutil.py` is the optional-import helper
- `src/machine_scanner/report/`     — json / text / html renderers
- `src/machine_scanner/cli.py`      — argparse entry point (`machine-scanner`)
- `tests/`                          — offline, hardware-agnostic pytest
- `build/`                          — per-OS packaging (PyInstaller) — F5
- `docs/`                           — STATE, ROADMAP, ARCHITECTURE, DECISIONS

## Conventions

- Python ≥ 3.9, type hints, `from __future__ import annotations`.
- A collector must **never raise** for an expected "absent" case (no GPU, no
  swap) — return `UNAVAILABLE`/`PARTIAL` with a note. Reserve exceptions (→
  `ERROR` section) for genuine bugs.
- New OS-specific probing goes through `core.platform.run_command` (guarded
  subprocess), never a bare `subprocess` call.
- Unit tests stay offline and make **no** assumption about the host's hardware.

## Watch for portfolio-worthy findings

This is a career-showcase repo. When something genuinely CV/post-worthy appears
(a clever cross-platform technique, a shipped capability, a number), note it for
my private engineering-findings log — even unprompted. Sanitize to the public
level (it's already clean-room, so stack/method are free to mention).

## Definition of done (per feature)

- Code + type hints + a focused offline test.
- `docs/STATE.md` updated (what changed, what's next); phase marked in `ROADMAP`.
- An ADR in `docs/DECISIONS.md` if a non-obvious choice was made.
