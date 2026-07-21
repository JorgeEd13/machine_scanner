"""machine_scanner — a portable, cross-platform machine inventory tool.

Plug it into any machine (Windows / Linux / macOS) and get a complete
inventory of hardware, OS and network — as JSON, plain text or an HTML report.

The public entry points are the registry runner and the report renderers:

    from machine_scanner.core.registry import run_all
    from machine_scanner.report.json_report import to_json

    inventory = run_all()
    print(to_json(inventory))
"""

__version__ = "0.2.1"
