"""HTML renderer — a single self-contained file you can drop next to the binary.

Deliberately dependency-free (no Jinja, no JS framework): inline CSS, one card
per section. A richer, interactive report is on the roadmap (F4); this is the
shareable artifact for now.
"""

from __future__ import annotations

import html
import json

from ..core.models import Inventory, Status

_STATUS_COLOR = {
    Status.OK: "#2e7d32",
    Status.PARTIAL: "#f9a825",
    Status.UNAVAILABLE: "#9e9e9e",
    Status.UNSUPPORTED: "#6a1b9a",
    Status.ERROR: "#c62828",
}

_CSS = """
body{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#f5f6f8;color:#222}
header{background:#1f2933;color:#fff;padding:20px 28px}
header h1{margin:0 0 6px;font-size:20px}
header .meta{font-size:13px;opacity:.85;line-height:1.5}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;padding:24px}
.card{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.12);overflow:hidden}
.card h2{margin:0;padding:12px 16px;font-size:15px;border-bottom:1px solid #eee;display:flex;
  justify-content:space-between;align-items:center}
.badge{font-size:11px;color:#fff;padding:2px 8px;border-radius:10px}
.card .body{padding:8px 16px 14px}
.row{display:flex;justify-content:space-between;gap:12px;padding:3px 0;font-size:13px;border-bottom:1px solid #f4f4f4}
.row .k{color:#666}.row .v{font-weight:600;text-align:right;word-break:break-word}
.note{color:#b26a00;font-size:12px;margin-top:8px}
pre{background:#fafafa;border:1px solid #eee;border-radius:6px;padding:8px;font-size:12px;overflow:auto}
"""


def _row(key: str, value: str) -> str:
    return f'<div class="row"><span class="k">{html.escape(key)}</span>' \
           f'<span class="v">{html.escape(value)}</span></div>'


def _render_data(data: dict) -> str:
    parts = []
    for key, value in data.items():
        if isinstance(value, (list, dict)):
            pretty = json.dumps(value, indent=2, ensure_ascii=False)
            parts.append(f'<div class="k" style="margin-top:8px">{html.escape(key)}</div>')
            parts.append(f"<pre>{html.escape(pretty)}</pre>")
        else:
            parts.append(_row(key, str(value)))
    return "".join(parts)


def to_html(inventory: Inventory) -> str:
    meta = inventory.meta
    cards = []
    for sec in inventory.sections:
        color = _STATUS_COLOR.get(sec.status, "#607d8b")
        notes = "".join(
            f'<div class="note">! {html.escape(n.splitlines()[0])}</div>'
            for n in sec.notes
        )
        cards.append(
            f'<div class="card"><h2>{html.escape(sec.title)}'
            f'<span class="badge" style="background:{color}">{sec.status.value}</span></h2>'
            f'<div class="body">{_render_data(sec.data)}{notes}</div></div>'
        )

    meta_html = (
        f"host: {html.escape(str(meta.get('hostname')))} &middot; "
        f"os: {html.escape(str(meta.get('os_detail')))}<br>"
        f"scanned: {html.escape(str(meta.get('scanned_at')))} &middot; "
        f"elevated: {html.escape(str(meta.get('elevated')))}"
    )

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>machine_scanner — {html.escape(str(meta.get('hostname')))}</title>"
        f"<style>{_CSS}</style></head><body>"
        f"<header><h1>machine_scanner v{html.escape(str(meta.get('version','?')))}</h1>"
        f"<div class='meta'>{meta_html}</div></header>"
        f"<main>{''.join(cards)}</main></body></html>"
    )
