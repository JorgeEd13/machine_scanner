"""JSON renderer — the machine-readable, archivable form of a scan."""

from __future__ import annotations

import json

from ..core.models import Inventory


def to_json(inventory: Inventory, indent: int = 2) -> str:
    """Render an Inventory as a JSON string (UTF-8 safe, stable shape)."""
    return json.dumps(inventory.to_dict(), indent=indent, ensure_ascii=False)
