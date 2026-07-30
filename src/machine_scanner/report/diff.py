"""Scan diff — "what changed on this machine" between two saved scans.

Two clearly separated halves, honouring the ADR-002 boundary one level up:

* ``diff_scans`` is the **pure, renderer-agnostic compute** — it takes two
  ``Inventory.to_dict()`` dicts (loaded from saved JSON, never a live re-scan)
  and returns a structured diff. It performs **no** rendering.
* ``diff_to_text`` / ``diff_to_html`` are **pure formatters** of that diff
  structure — they perform **no** comparison. Either renderer can display the
  same diff object.

The diff is keyed on the stable section ``name`` and, within a section, a
deterministic path into the (possibly nested) data: dict keys join with ``.``
and list elements index with ``[i]`` (e.g. ``data.devices[2].name``). Paths are
*deterministic* (same inputs → same path), which is what makes a diff
reproducible; they are index-based, so a reordered list shows as field changes
rather than a move — an accepted, honest trade-off for an inventory diff.
"""

from __future__ import annotations

import html
import json
from typing import Any

# ---------------------------------------------------------------------------
# Compute  (pure — no rendering)
# ---------------------------------------------------------------------------


def _ordered_union(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Keys of ``old`` in order, then keys only in ``new`` — deterministic."""
    keys = list(old.keys())
    keys.extend(k for k in new if k not in old)
    return keys


def _diff_value(path: str, old: Any, new: Any, out: list[dict[str, Any]]) -> None:
    """Recurse two values, appending field-level changes to ``out``."""
    if isinstance(old, dict) and isinstance(new, dict):
        for key in _ordered_union(old, new):
            cpath = f"{path}.{key}" if path else str(key)
            if key not in old:
                out.append({"path": cpath, "kind": "added", "old": None, "new": new[key]})
            elif key not in new:
                out.append({"path": cpath, "kind": "removed", "old": old[key], "new": None})
            else:
                _diff_value(cpath, old[key], new[key], out)
    elif isinstance(old, list) and isinstance(new, list):
        for i in range(max(len(old), len(new))):
            cpath = f"{path}[{i}]"
            if i >= len(old):
                out.append({"path": cpath, "kind": "added", "old": None, "new": new[i]})
            elif i >= len(new):
                out.append({"path": cpath, "kind": "removed", "old": old[i], "new": None})
            else:
                _diff_value(cpath, old[i], new[i], out)
    elif old != new:
        out.append({"path": path, "kind": "changed", "old": old, "new": new})


def _sections_by_name(scan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s.get("name"): s for s in scan.get("sections", [])}


def _section_brief(sec: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": sec.get("name"),
        "title": sec.get("title", sec.get("name")),
        "status": sec.get("status"),
    }


def diff_scans(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Compare two ``Inventory.to_dict()`` scans into a structured diff.

    Returns a dict with ``old_meta`` / ``new_meta`` and three buckets:
    ``sections_added`` / ``sections_removed`` (each a list of
    ``{name, title, status}``) and ``sections_changed`` (a list of
    ``{name, title, changes:[{path, kind, old, new}]}``). A section that is
    present in both and identical does not appear anywhere — an unchanged scan
    yields three empty buckets.
    """
    old_secs = _sections_by_name(old)
    new_secs = _sections_by_name(new)

    added = [
        _section_brief(new_secs[name])
        for name in new_secs
        if name not in old_secs
    ]
    removed = [
        _section_brief(old_secs[name])
        for name in old_secs
        if name not in new_secs
    ]

    changed: list[dict[str, Any]] = []
    for name, old_sec in old_secs.items():
        if name not in new_secs:
            continue
        new_sec = new_secs[name]
        changes: list[dict[str, Any]] = []
        # Compare the meaningful section payload: status, data, notes.
        # (name/title are identity and excluded.)
        old_cmp = {
            "status": old_sec.get("status"),
            "data": old_sec.get("data", {}),
            "notes": old_sec.get("notes", []),
        }
        new_cmp = {
            "status": new_sec.get("status"),
            "data": new_sec.get("data", {}),
            "notes": new_sec.get("notes", []),
        }
        _diff_value("", old_cmp, new_cmp, changes)
        if changes:
            changed.append(
                {
                    "name": name,
                    "title": new_sec.get("title", name),
                    "changes": changes,
                }
            )

    return {
        "old_meta": old.get("meta", {}),
        "new_meta": new.get("meta", {}),
        "sections_added": added,
        "sections_removed": removed,
        "sections_changed": changed,
    }


def has_changes(diff: dict[str, Any]) -> bool:
    """True if the diff contains any added / removed / changed section."""
    return bool(
        diff.get("sections_added")
        or diff.get("sections_removed")
        or diff.get("sections_changed")
    )


# ---------------------------------------------------------------------------
# Render  (pure formatters — no comparison)
# ---------------------------------------------------------------------------


def _fmt_scalar(value: Any) -> str:
    if value is None:
        return "∅"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _meta_line(meta: dict[str, Any]) -> str:
    return f"{meta.get('hostname', '?')} @ {meta.get('scanned_at', '?')}"


def diff_to_text(diff: dict[str, Any]) -> str:
    """Render a diff structure as a plain-text report."""
    out: list[str] = []
    out.append("=" * 64)
    out.append("  machine_scanner — scan diff")
    out.append("=" * 64)
    out.append(f"old : {_meta_line(diff.get('old_meta', {}))}")
    out.append(f"new : {_meta_line(diff.get('new_meta', {}))}")

    if not has_changes(diff):
        out.append("")
        out.append("no differences — the two scans are identical.")
        out.append("")
        return "\n".join(out)

    for sec in diff.get("sections_added", []):
        out.append("")
        out.append(f"+ section added: {sec['title']} ({sec['name']}) [{sec['status']}]")
    for sec in diff.get("sections_removed", []):
        out.append("")
        out.append(f"- section removed: {sec['title']} ({sec['name']}) [{sec['status']}]")

    for sec in diff.get("sections_changed", []):
        out.append("")
        out.append(f"~ {sec['title']} ({sec['name']})")
        for ch in sec["changes"]:
            kind = ch["kind"]
            if kind == "added":
                out.append(f"    + {ch['path']}: {_fmt_scalar(ch['new'])}")
            elif kind == "removed":
                out.append(f"    - {ch['path']}: {_fmt_scalar(ch['old'])}")
            else:
                out.append(
                    f"    ~ {ch['path']}: {_fmt_scalar(ch['old'])} -> {_fmt_scalar(ch['new'])}"
                )

    out.append("")
    return "\n".join(out)


_DIFF_CSS = """
body{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#f5f6f8;color:#222}
header{background:#1f2933;color:#fff;padding:20px 28px}
header h1{margin:0 0 8px;font-size:20px}
header .meta{font-size:13px;opacity:.85;line-height:1.6}
main{padding:24px;max-width:960px;margin:0 auto}
.none{background:#fff;border-radius:10px;padding:28px;text-align:center;color:#2e7d32;font-weight:600;
  box-shadow:0 1px 3px rgba(0,0,0,.12)}
.sec{background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.12);margin-bottom:16px;overflow:hidden}
.sec h2{margin:0;padding:12px 16px;font-size:15px;border-bottom:1px solid #eee;display:flex;
  justify-content:space-between;align-items:center;gap:8px}
.tag{font-size:11px;color:#fff;padding:2px 8px;border-radius:10px;font-weight:600}
.tag.add{background:#2e7d32}.tag.rem{background:#c62828}.tag.chg{background:#1565c0}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:6px 16px;text-align:left;border-bottom:1px solid #f1f1f1;vertical-align:top;word-break:break-word}
th{color:#666;font-weight:600;background:#fafbfc}
td.path{font-family:ui-monospace,Consolas,monospace;color:#37474f;white-space:nowrap}
.k-added{color:#2e7d32;font-weight:600}.k-removed{color:#c62828;font-weight:600}.k-changed{color:#1565c0;font-weight:600}
.old{color:#c62828}.new{color:#2e7d32}
.body{padding:6px 0}
"""


def _row_cells(ch: dict[str, Any]) -> str:
    kind = ch["kind"]
    path = html.escape(ch["path"])
    if kind == "added":
        val = f'<span class="new">{html.escape(_fmt_scalar(ch["new"]))}</span>'
    elif kind == "removed":
        val = f'<span class="old">{html.escape(_fmt_scalar(ch["old"]))}</span>'
    else:
        val = (
            f'<span class="old">{html.escape(_fmt_scalar(ch["old"]))}</span>'
            " &rarr; "
            f'<span class="new">{html.escape(_fmt_scalar(ch["new"]))}</span>'
        )
    return (
        f'<tr><td class="path">{path}</td>'
        f'<td class="k-{kind}">{kind}</td><td>{val}</td></tr>'
    )


def diff_to_html(diff: dict[str, Any]) -> str:
    """Render a diff structure as a single self-contained HTML page."""
    old_m = diff.get("old_meta", {})
    new_m = diff.get("new_meta", {})

    if not has_changes(diff):
        body = '<div class="none">No differences — the two scans are identical.</div>'
    else:
        blocks: list[str] = []
        for sec in diff.get("sections_added", []):
            blocks.append(
                f'<div class="sec"><h2><span>{html.escape(sec["title"])} '
                f'<small>({html.escape(sec["name"])})</small></span>'
                f'<span class="tag add">section added</span></h2></div>'
            )
        for sec in diff.get("sections_removed", []):
            blocks.append(
                f'<div class="sec"><h2><span>{html.escape(sec["title"])} '
                f'<small>({html.escape(sec["name"])})</small></span>'
                f'<span class="tag rem">section removed</span></h2></div>'
            )
        for sec in diff.get("sections_changed", []):
            rows = "".join(_row_cells(ch) for ch in sec["changes"])
            blocks.append(
                f'<div class="sec"><h2><span>{html.escape(sec["title"])} '
                f'<small>({html.escape(sec["name"])})</small></span>'
                f'<span class="tag chg">{len(sec["changes"])} change(s)</span></h2>'
                f'<div class="body"><table>'
                f"<thead><tr><th>path</th><th>kind</th><th>value</th></tr></thead>"
                f"<tbody>{rows}</tbody></table></div></div>"
            )
        body = "".join(blocks)

    meta_html = (
        f"old: {html.escape(_meta_line(old_m))}<br>"
        f"new: {html.escape(_meta_line(new_m))}"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>machine_scanner — scan diff</title>"
        f"<style>{_DIFF_CSS}</style></head><body>"
        "<header><h1>machine_scanner — scan diff</h1>"
        f"<div class='meta'>{meta_html}</div></header>"
        f"<main>{body}</main></body></html>"
    )
