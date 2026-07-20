"""HTML renderer — a single self-contained, interactive file (F4).

One ``.card`` per section, but now *interactive*: sections are collapsible,
a search box filters by section name / key / value, and any section (or the
whole scan) can be copied as JSON. Nested data is rendered as a readable tree
(recursing to any depth, the HTML twin of the text renderer's ADR-007), not a
raw ``<pre>`` JSON dump.

Constraints (ADR-015): the file is fully **self-contained** — inline CSS and
inline *vanilla* JS, no framework, no CDN, no external ``src``/``href``. With
JavaScript disabled it degrades to a readable static document: ``<details>``
gives native collapse, every section is laid out as a tree, and only the
search box / copy buttons go inert.
"""

from __future__ import annotations

import html
import json
from typing import Any, List, Mapping, Sequence

from ..core.models import Inventory, Section, Status
from .brand import FAVICON_LINK as _FAVICON_LINK

_STATUS_COLOR = {
    Status.OK: "#2e7d32",
    Status.PARTIAL: "#f9a825",
    Status.UNAVAILABLE: "#9e9e9e",
    Status.UNSUPPORTED: "#6a1b9a",
    Status.ERROR: "#c62828",
}


_CSS = """
*{box-sizing:border-box}
body{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#f5f6f8;color:#222}
header{background:#1f2933;color:#fff;padding:20px 28px}
header h1{margin:0 0 6px;font-size:20px}
header .meta{font-size:13px;opacity:.85;line-height:1.5}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;align-items:center}
.toolbar input[type=search]{flex:1 1 240px;min-width:180px;padding:7px 10px;border:1px solid #3b4754;
  border-radius:6px;background:#fff;color:#222;font-size:13px}
button{font:inherit;font-size:12px;padding:6px 10px;border:1px solid #3b4754;border-radius:6px;
  background:#2b3744;color:#fff;cursor:pointer}
button:hover{background:#3b4a5a}
.card button{border-color:#ccc;background:#f3f4f6;color:#333}
.card button:hover{background:#e7e9ee}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;padding:24px}
.card{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.12);overflow:hidden}
.card>summary{list-style:none;cursor:pointer;padding:12px 16px;font-size:15px;font-weight:600;
  border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center;gap:8px}
.card>summary::-webkit-details-marker{display:none}
.card>summary:hover{background:#fafbfc}
.summary-left{display:flex;align-items:center;gap:8px;min-width:0}
.summary-left .caret{transition:transform .15s;color:#999;font-size:11px}
.card[open]>summary .caret{transform:rotate(90deg)}
.summary-left .title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.summary-right{display:flex;align-items:center;gap:8px;flex:none}
.badge{font-size:11px;color:#fff;padding:2px 8px;border-radius:10px;font-weight:600}
.card .body{padding:8px 16px 14px}
.kv{display:flex;justify-content:space-between;gap:12px;padding:3px 0;font-size:13px;border-bottom:1px solid #f4f4f4}
.kv .k{color:#666}.kv .v{font-weight:600;text-align:right;word-break:break-word}
.nest{padding:4px 0}
.nk{color:#37474f;font-weight:600;font-size:13px;margin:4px 0 2px}
.sub{margin-left:12px;border-left:2px solid #eef0f3;padding-left:10px}
.recs .rec{padding:4px 0}
.recs .rec+.rec{border-top:1px dashed #e6e8ec;margin-top:4px;padding-top:8px}
ul.lst{margin:2px 0;padding-left:18px;font-size:13px}
ul.lst li{word-break:break-word}
.muted{color:#9aa0a6;font-size:13px;font-style:italic}
.note{color:#b26a00;font-size:12px;margin-top:8px}
.empty{color:#9aa0a6;font-size:13px;padding:20px;text-align:center}
pre{background:#fafafa;border:1px solid #eee;border-radius:6px;padding:8px;font-size:12px;overflow:auto}
"""

# Vanilla JS, no framework. Kept out of the f-string assembly because it is full
# of braces. Wires the search box, copy buttons and expand/collapse-all.
_JS = """
(function(){
  function copyText(text, btn){
    var label = btn.textContent;
    function done(){ btn.textContent = 'copied'; setTimeout(function(){ btn.textContent = label; }, 1200); }
    function fallback(){
      var ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.focus(); ta.select();
      try { document.execCommand('copy'); } catch(e) {}
      document.body.removeChild(ta);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function(){ fallback(); done(); });
    } else { fallback(); done(); }
  }
  document.querySelectorAll('[data-copy-json]').forEach(function(btn){
    btn.addEventListener('click', function(e){
      e.preventDefault(); e.stopPropagation();
      copyText(btn.getAttribute('data-copy-json'), btn);
    });
  });
  function setAll(open){ document.querySelectorAll('details.card').forEach(function(d){ d.open = open; }); }
  var ea = document.getElementById('expand-all');
  if (ea) ea.addEventListener('click', function(){ setAll(true); });
  var ca = document.getElementById('collapse-all');
  if (ca) ca.addEventListener('click', function(){ setAll(false); });
  var search = document.getElementById('search');
  var empty = document.getElementById('no-matches');
  if (search) {
    search.addEventListener('input', function(){
      var q = this.value.toLowerCase().trim();
      var shown = 0;
      document.querySelectorAll('details.card').forEach(function(card){
        var hay = card.getAttribute('data-search') || '';
        var match = q === '' || hay.indexOf(q) !== -1;
        card.style.display = match ? '' : 'none';
        if (match) { shown++; if (q !== '') card.open = true; }
      });
      if (empty) empty.style.display = shown === 0 ? '' : 'none';
    });
  }
})();
"""


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _is_list(value: Any) -> bool:
    # str/bytes are Sequences too — exclude them, they are scalars here.
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _render_mapping(mapping: Mapping[str, Any]) -> str:
    """Render a dict as key/value rows, recursing into nested containers."""
    rows: List[str] = []
    for key, value in mapping.items():
        klabel = html.escape(str(key))
        if _is_mapping(value) or _is_list(value):
            rows.append(
                f'<div class="nest"><div class="nk">{klabel}</div>'
                f'<div class="sub">{_render_value(value)}</div></div>'
            )
        else:
            rows.append(
                f'<div class="kv"><span class="k">{klabel}</span>'
                f'<span class="v">{html.escape(_scalar(value))}</span></div>'
            )
    if not rows:
        return '<span class="muted">(empty)</span>'
    return "".join(rows)


def _render_value(value: Any) -> str:
    """Render any value as an HTML tree, recursing to arbitrary depth.

    The recursion is the structural twin of the text renderer (ADR-007): dicts
    become key/value rows, lists of scalars become a ``<ul>``, lists of records
    become stacked blocks, an empty list reads ``(none)``. ``<pre>`` is reserved
    as a leaf fallback for a value that is somehow neither mapping, list nor
    scalar — it is never used to dump a whole nested structure.
    """
    if _is_mapping(value):
        return _render_mapping(value)
    if _is_list(value):
        if not value:
            return '<span class="muted">(none)</span>'
        if all(not _is_mapping(i) and not _is_list(i) for i in value):
            lis = "".join(f"<li>{html.escape(_scalar(i))}</li>" for i in value)
            return f'<ul class="lst">{lis}</ul>'
        recs = "".join(f'<div class="rec">{_render_value(i)}</div>' for i in value)
        return f'<div class="recs">{recs}</div>'
    if isinstance(value, (str, bytes, int, float, bool)) or value is None:
        return f'<span class="v">{html.escape(_scalar(value))}</span>'
    # leaf fallback — an unexpected type we couldn't classify
    return f"<pre>{html.escape(str(value))}</pre>"


def _flatten_text(value: Any) -> List[str]:
    """Collect every key and scalar into a flat list (for the search index)."""
    out: List[str] = []
    if _is_mapping(value):
        for key, val in value.items():
            out.append(str(key))
            out.extend(_flatten_text(val))
    elif _is_list(value):
        for item in value:
            out.extend(_flatten_text(item))
    else:
        out.append(_scalar(value))
    return out


def _section_dict(sec: Section) -> dict:
    return {
        "name": sec.name,
        "title": sec.title,
        "status": sec.status.value,
        "data": sec.data,
        "notes": sec.notes,
    }


def _card(sec: Section) -> str:
    color = _STATUS_COLOR.get(sec.status, "#607d8b")
    notes = "".join(
        f'<div class="note">! {html.escape(n.splitlines()[0])}</div>' for n in sec.notes
    )
    haystack = " ".join(
        [sec.name, sec.title] + _flatten_text(sec.data) + list(sec.notes)
    ).lower()
    sec_json = json.dumps(_section_dict(sec), ensure_ascii=False, indent=2)
    body = _render_value(sec.data) if sec.data else '<span class="muted">(no data)</span>'
    return (
        f'<details class="card" open data-search="{html.escape(haystack)}">'
        f'<summary><span class="summary-left">'
        f'<span class="caret">&#9654;</span>'
        f'<span class="title">{html.escape(sec.title)}</span></span>'
        f'<span class="summary-right">'
        f'<span class="badge" style="background:{color}">{sec.status.value}</span>'
        f'<button type="button" data-copy-json="{html.escape(sec_json)}">copy JSON</button>'
        f'</span></summary>'
        f'<div class="body">{body}{notes}</div></details>'
    )


def to_html(inventory: Inventory) -> str:
    meta = inventory.meta
    cards = "".join(_card(sec) for sec in inventory.sections)
    all_json = json.dumps(inventory.to_dict(), ensure_ascii=False, indent=2)

    meta_html = (
        f"host: {html.escape(str(meta.get('hostname')))} &middot; "
        f"os: {html.escape(str(meta.get('os_detail')))}<br>"
        f"scanned: {html.escape(str(meta.get('scanned_at')))} &middot; "
        f"elevated: {html.escape(str(meta.get('elevated')))}"
    )

    head = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>machine_scanner — {html.escape(str(meta.get('hostname')))}</title>"
        f"{_FAVICON_LINK}"
        f"<style>{_CSS}</style></head><body>"
    )
    header = (
        f"<header><h1>machine_scanner v{html.escape(str(meta.get('version', '?')))}</h1>"
        f"<div class='meta'>{meta_html}</div>"
        "<div class='toolbar'>"
        "<input id='search' type='search' placeholder='filter sections, keys, values…' autocomplete='off'>"
        f"<button type='button' data-copy-json=\"{html.escape(all_json)}\">copy all JSON</button>"
        "<button type='button' id='expand-all'>expand all</button>"
        "<button type='button' id='collapse-all'>collapse all</button>"
        "</div></header>"
    )
    body = (
        f"<main>{cards}</main>"
        "<div id='no-matches' class='empty' style='display:none'>no sections match your filter</div>"
        f"<script>{_JS}</script></body></html>"
    )
    return head + header + body
