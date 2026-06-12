"""Frozen-binary entry point.

PyInstaller runs the entry script as ``__main__``, so the package's own
``__main__.py`` (which uses a relative ``from .cli import main``) can't be the
target — a relative import has no parent package here. This thin wrapper does
the absolute import instead. The spec puts ``src/`` on the analysis path so
``machine_scanner`` resolves; the explicit imports in
``machine_scanner.collectors.__init__`` (ADR-002) are what let PyInstaller's
static analysis discover and bundle every collector.
"""

import sys

from machine_scanner.cli import main

if __name__ == "__main__":
    sys.exit(main())
