"""Tests for the scan diff (F4) — pure compute + the two formatters.

Offline: synthetic ``Inventory.to_dict()``-shaped dicts, built inline (no real
committed scans). Covers the no-change case, section add/remove, and
field-level changes in nested data; plus a smoke check of each renderer.
"""

from machine_scanner.report.diff import (
    diff_scans,
    diff_to_html,
    diff_to_text,
    has_changes,
)


def _scan(*sections, hostname="box"):
    return {
        "meta": {"hostname": hostname, "scanned_at": "2026-06-11T00:00:00"},
        "sections": list(sections),
    }


def _sec(name, title=None, status="ok", data=None, notes=None):
    return {
        "name": name,
        "title": title or name.upper(),
        "status": status,
        "data": data or {},
        "notes": notes or [],
    }


# --- no change -------------------------------------------------------------


def test_identical_scans_yield_empty_diff():
    scan = _scan(_sec("cpu", data={"cores": 8}))
    diff = diff_scans(scan, scan)
    assert diff["sections_added"] == []
    assert diff["sections_removed"] == []
    assert diff["sections_changed"] == []
    assert has_changes(diff) is False


# --- section add / remove --------------------------------------------------


def test_section_added_and_removed():
    old = _scan(_sec("cpu"), _sec("gpu"))
    new = _scan(_sec("cpu"), _sec("battery"))
    diff = diff_scans(old, new)

    added = [s["name"] for s in diff["sections_added"]]
    removed = [s["name"] for s in diff["sections_removed"]]
    assert added == ["battery"]
    assert removed == ["gpu"]
    # unchanged "cpu" is not reported anywhere
    assert diff["sections_changed"] == []
    assert has_changes(diff) is True


# --- field-level changes ---------------------------------------------------


def test_scalar_field_change_is_detected():
    old = _scan(_sec("cpu", data={"cores": 4}))
    new = _scan(_sec("cpu", data={"cores": 8}))
    diff = diff_scans(old, new)

    changed = diff["sections_changed"]
    assert len(changed) == 1
    assert changed[0]["name"] == "cpu"
    ch = changed[0]["changes"]
    paths = {c["path"]: c for c in ch}
    assert "data.cores" in paths
    assert paths["data.cores"]["kind"] == "changed"
    assert paths["data.cores"]["old"] == 4
    assert paths["data.cores"]["new"] == 8


def test_status_change_is_detected():
    old = _scan(_sec("battery", status="ok", data={"percent": 90}))
    new = _scan(_sec("battery", status="unavailable", data={"percent": 90}))
    diff = diff_scans(old, new)
    ch = diff["sections_changed"][0]["changes"]
    paths = {c["path"]: c for c in ch}
    assert paths["status"]["old"] == "ok"
    assert paths["status"]["new"] == "unavailable"


def test_nested_list_field_change_uses_indexed_path():
    old = _scan(
        _sec("usb", data={"devices": [{"name": "kbd", "vid": "046d"}]})
    )
    new = _scan(
        _sec("usb", data={"devices": [{"name": "kbd", "vid": "1234"}]})
    )
    diff = diff_scans(old, new)
    ch = diff["sections_changed"][0]["changes"]
    paths = {c["path"]: c for c in ch}
    assert "data.devices[0].vid" in paths
    assert paths["data.devices[0].vid"]["old"] == "046d"
    assert paths["data.devices[0].vid"]["new"] == "1234"


def test_added_and_removed_keys_within_data():
    old = _scan(_sec("cpu", data={"cores": 4, "old_field": "x"}))
    new = _scan(_sec("cpu", data={"cores": 4, "new_field": "y"}))
    diff = diff_scans(old, new)
    ch = diff["sections_changed"][0]["changes"]
    by_path = {c["path"]: c for c in ch}
    assert by_path["data.new_field"]["kind"] == "added"
    assert by_path["data.new_field"]["new"] == "y"
    assert by_path["data.old_field"]["kind"] == "removed"
    assert by_path["data.old_field"]["old"] == "x"


def test_list_grew_reports_added_index():
    old = _scan(_sec("usb", data={"devices": [{"name": "a"}]}))
    new = _scan(_sec("usb", data={"devices": [{"name": "a"}, {"name": "b"}]}))
    diff = diff_scans(old, new)
    ch = diff["sections_changed"][0]["changes"]
    paths = {c["path"]: c for c in ch}
    assert "data.devices[1]" in paths
    assert paths["data.devices[1]"]["kind"] == "added"
    assert paths["data.devices[1]"]["new"] == {"name": "b"}


# --- renderers (pure formatters) -------------------------------------------


def test_text_renderer_no_change_message():
    scan = _scan(_sec("cpu", data={"cores": 8}))
    text = diff_to_text(diff_scans(scan, scan))
    assert "no differences" in text.lower()


def test_text_renderer_shows_changes():
    old = _scan(_sec("cpu", data={"cores": 4}), _sec("gpu"))
    new = _scan(_sec("cpu", data={"cores": 8}))
    text = diff_to_text(diff_scans(old, new))
    assert "data.cores" in text
    assert "4" in text and "8" in text
    assert "gpu" in text  # removed section mentioned


def test_html_diff_is_self_contained():
    old = _scan(_sec("cpu", data={"cores": 4}))
    new = _scan(_sec("cpu", data={"cores": 8}))
    out = diff_to_html(diff_scans(old, new))
    assert out.startswith("<!doctype html>")
    assert "http://" not in out and "https://" not in out
    assert "src=" not in out and "href=" not in out
    assert "data.cores" in out


def test_html_diff_no_change_page():
    scan = _scan(_sec("cpu", data={"cores": 8}))
    out = diff_to_html(diff_scans(scan, scan))
    assert "identical" in out.lower()
