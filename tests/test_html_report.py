"""Tests for the interactive HTML renderer (F4).

Offline and hardware-agnostic: a synthetic Inventory drives the renderer. These
lock the F4 contract — self-containment (no external assets), the interactive
scaffolding (search / collapse / copy), and nested data rendered as a tree
rather than a raw ``<pre>`` JSON dump.
"""

import re

from machine_scanner.core.models import Inventory, Section, Status
from machine_scanner.report.html_report import to_html


def _inventory() -> Inventory:
    return Inventory(
        meta={
            "version": "0.1.0",
            "hostname": "test-box",
            "os_detail": "TestOS 1.0",
            "scanned_at": "2026-06-11T00:00:00",
            "elevated": False,
        },
        sections=[
            Section("cpu", "CPU", Status.OK, {"cores_logical": 8, "brand": "TestCPU"}),
            Section(
                "network",
                "Network",
                Status.OK,
                {
                    "interfaces": [
                        {
                            "name": "eth0",
                            "addresses": [
                                {"family": "AF_INET", "address": "192.168.0.5"},
                            ],
                            "is_up": True,
                        }
                    ]
                },
            ),
            Section("gpu", "GPU", Status.UNAVAILABLE, {}, notes=["no discrete GPU"]),
        ],
    )


def test_html_is_self_contained_no_external_assets():
    out = to_html(_inventory())
    # No remote protocols anywhere.
    assert "http://" not in out
    assert "https://" not in out
    # Any src/href must be an inline ``data:`` URI (e.g. the favicon), never a
    # remote fetch — the report stays one self-contained file (ADR-015).
    for m in re.finditer(r"""\b(?:src|href)\s*=\s*(['"])(.*?)\1""", out):
        assert m.group(2).startswith("data:"), f"external asset ref: {m.group(2)[:50]}"
    # CSS and JS are inlined.
    assert "<style>" in out and "<script>" in out


def test_favicon_is_inlined_data_uri():
    out = to_html(_inventory())
    assert "rel='icon'" in out
    assert "href='data:image/png;base64," in out


def test_interactive_scaffolding_present():
    out = to_html(_inventory())
    # Search box.
    assert "id='search'" in out or 'id="search"' in out
    # Collapse: native <details> sections + expand/collapse-all controls.
    assert "<details" in out
    assert "expand-all" in out and "collapse-all" in out
    # Copy-as-JSON: per-section and whole-scan payloads.
    assert out.count("data-copy-json") >= 4  # 3 sections + 1 "copy all"


def test_nested_data_rendered_as_tree_not_pre_dump():
    out = to_html(_inventory())
    # The nested address must appear as real rendered values, not buried in a
    # single <pre> JSON blob.
    assert "192.168.0.5" in out
    assert "AF_INET" in out
    assert "eth0" in out
    # The old static renderer dumped nested data as indented JSON inside <pre>;
    # the tree must not do that.
    assert "<pre>{" not in out
    # Tree markup is present (nested key + indented sub-block).
    assert 'class="nest"' in out
    assert 'class="sub"' in out


def test_section_status_and_notes_render():
    out = to_html(_inventory())
    assert "unavailable" in out
    assert "no discrete GPU" in out


def test_copy_payload_contains_section_json():
    out = to_html(_inventory())
    # The per-section JSON is embedded HTML-escaped in the copy button. The
    # escaped form of the cpu section's data must be present.
    assert "cores_logical" in out
    # whole-scan copy includes the meta block
    assert "test-box" in out


def test_search_index_lowercased_and_present():
    out = to_html(_inventory())
    # data-search holds a lowercase haystack including keys and values.
    assert "data-search=" in out
    assert "testcpu" in out  # value "TestCPU" lowercased into the index
