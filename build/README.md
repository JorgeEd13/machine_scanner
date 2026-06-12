# build/ — packaging (ROADMAP F5)

Per-OS packaging. The "plug into any machine" goal can't be one binary — a
PyInstaller `.exe` runs only on Windows — so the deliverable is **one binary per
OS, built from one spec**, plus the raw Python script wherever Python exists.

## Files here (committed)

- [`machine_scanner.spec`](machine_scanner.spec) — the one-file PyInstaller spec.
  It picks the artifact name from the build OS (`machine-scanner-windows.exe` /
  `-linux` / `-macos`), puts `src/` on the analysis path, and lists every
  collector as a `hiddenimport` (belt-and-suspenders over ADR-002's self-
  registration). Embeds `machine_scanner.ico` if present.
- [`entrypoint.py`](entrypoint.py) — thin entry script (absolute import of
  `machine_scanner.cli:main`); a PyInstaller entry runs as `__main__`, so the
  package's relative-import `__main__.py` can't be the target.
- `machine_scanner.ico` — the brand hypercube as a multi-resolution Windows icon
  (16–256 px; the small sizes use a bolder crop of the cyan inner cube so the
  mark survives at 16 px). Derived from the project logo, committed as a binary
  asset. The same mark is inlined as the HTML report's favicon (ADR-015 addendum).

Build output (`dist/`, `build/<name>/`) is git-ignored — binaries are built by
the release workflow, never committed.

## Building locally

```sh
python -m pip install -e ".[build]"      # pyinstaller, build-time only
pyinstaller build/machine_scanner.spec   # -> dist/machine-scanner-<os>[.exe]
```

`pyinstaller` is a **build-time** dependency only (a `[build]` extra), never a
runtime dep and never in `requirements.txt` — psutil stays the single runtime
dependency (ADR-001).

## Releasing

Push a `v*` tag. [`.github/workflows/release.yml`](../.github/workflows/release.yml)
builds the binary on `windows-latest`, `ubuntu-latest` and `macos-latest`,
smoke-tests each (`--list` must show all 16 collectors), and uploads the three
to a GitHub Release. macOS and Linux binaries come from those runners — they
can't be built on a Windows dev box (and WSL here has no `pip`).

---

## USB-stick layout — "plug into anything"

Drop the three binaries on a stick. On any machine, run the one for its OS — no
Python, no install, no network:

```
machine-scanner/
├─ machine-scanner-windows.exe     ← Windows: double-click or run in a terminal
├─ machine-scanner-linux           ← Linux:  chmod +x once, then ./machine-scanner-linux
├─ machine-scanner-macos           ← macOS:  chmod +x once, then ./machine-scanner-macos
└─ src/  (optional)                ← the Python fallback: `python -m machine_scanner`
```

**Usage.** Double-clicking the binary (no arguments) scans the machine, writes a
self-contained HTML report next to itself and opens it in the browser — the
filename is localized to the OS language (`machine_inventory.html`, or
`inventario_de_maquina.html` on a PT-BR box; report *content* stays English).
From a terminal the full CLI is there: `--json`, `--html -o report.html`,
`--only cpu,memory`, `--diff old.json new.json`, `--report`, `--list`. The HTML
report is a single file with no external assets, so it travels on the stick too.

**The fallback.** Where a binary won't run (an unsupported CPU arch, a locked-
down box) but Python ≥ 3.9 is present, copy `src/` and run
`PYTHONPATH=src python -m machine_scanner` — same tool, same output.

**Caveats.** The one-file binary unpacks to a temp dir on first run, so the
first launch is a few seconds slower than later ones. The binaries are
**unsigned**, so SmartScreen (Windows) or Gatekeeper (macOS) may warn on first
run — expected for an unsigned open-source tool; the source and the build
workflow are right here in the repo.
