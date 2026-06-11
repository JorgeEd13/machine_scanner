# build/

Per-OS packaging lives here (ROADMAP **F5**). The plan: one PyInstaller
one-file spec per target so the same codebase ships as
`machine-scanner-windows.exe`, `machine-scanner-linux`, and
`machine-scanner-macos` — the realistic answer to "one stick, plug into
anything" (a single binary cannot run on every OS).

Nothing here yet. Build artifacts (`build/<name>/`, `dist/`) are git-ignored;
only the spec files and this note are committed.
