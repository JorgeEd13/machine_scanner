"""Report renderers — turn an Inventory into JSON, text or HTML.

Renderers walk ``Inventory.sections`` generically and never import collectors,
so any new collector is picked up automatically.
"""

from .diff import diff_scans, diff_to_html, diff_to_text, has_changes
from .html_report import to_html
from .json_report import to_json
from .text_report import to_text

__all__ = [
    "diff_scans",
    "diff_to_html",
    "diff_to_text",
    "has_changes",
    "to_html",
    "to_json",
    "to_text",
]
