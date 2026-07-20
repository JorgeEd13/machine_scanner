"""Frozen-binary entry point for the requirements checker.

Twin of ``entrypoint.py`` (same reason for existing: PyInstaller runs the entry
script as ``__main__``, so a relative import has no parent package), pointing at
``machine_scanner.qualifier`` instead of the full CLI.

Two entry points rather than one binary with a flag, because the audience is
different: this one is handed to someone who did not go looking for it, and
"double-click, read the page" has to be the whole interaction.
"""

import sys

from machine_scanner.qualifier import main

if __name__ == "__main__":
    sys.exit(main())
