"""Report renderers — turn an Inventory into JSON, text or HTML.

Renderers walk ``Inventory.sections`` generically and never import collectors,
so any new collector is picked up automatically.
"""

from .json_report import to_json
from .text_report import to_text
from .html_report import to_html

__all__ = ["to_json", "to_text", "to_html"]
