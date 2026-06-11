"""CLI-level tests — exit codes and the basic output paths.

Offline and hardware-agnostic: we drive ``cli.main`` directly and, where the
result must be deterministic, stub the scan with a controlled Inventory.
"""

import json

import machine_scanner.cli as cli
from machine_scanner.core.models import Inventory, Section, Status


def _stub_scan(monkeypatch, *sections: Section) -> None:
    inv = Inventory(meta={"version": "0.1.0"}, sections=list(sections))
    monkeypatch.setattr(cli, "run_all", lambda only=None: inv)


def test_clean_scan_exits_zero(monkeypatch, capsys):
    _stub_scan(monkeypatch, Section("cpu", "CPU", Status.OK, {"cores_logical": 4}))
    assert cli.main([]) == cli.EXIT_OK


def test_partial_scan_still_exits_zero(monkeypatch, capsys):
    # An expected gap is not a failure.
    _stub_scan(monkeypatch, Section("gpu", "GPU", Status.UNAVAILABLE))
    assert cli.main([]) == cli.EXIT_OK


def test_errored_collector_exits_nonzero(monkeypatch, capsys):
    _stub_scan(
        monkeypatch,
        Section("cpu", "CPU", Status.OK, {"cores_logical": 4}),
        Section("boom", "BOOM", Status.ERROR, notes=["RuntimeError: kaboom"]),
    )
    assert cli.main([]) == cli.EXIT_COLLECTOR_ERROR


def test_list_exits_zero(monkeypatch, capsys):
    assert cli.main(["--list"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "cpu" in out


def test_json_output_is_emitted(monkeypatch, capsys):
    _stub_scan(monkeypatch, Section("cpu", "CPU", Status.OK, {"cores_logical": 4}))
    cli.main(["--json"])
    out = capsys.readouterr().out
    assert '"cores_logical": 4' in out


def _write_scan(path, cores):
    inv = Inventory(
        meta={"hostname": "box", "scanned_at": "t"},
        sections=[Section("cpu", "CPU", Status.OK, {"cores": cores})],
    )
    path.write_text(json.dumps(inv.to_dict()), encoding="utf-8")
    return str(path)


def test_diff_two_saved_scans_text(tmp_path, capsys):
    old = _write_scan(tmp_path / "old.json", 4)
    new = _write_scan(tmp_path / "new.json", 8)
    assert cli.main(["--diff", old, new]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "data.cores" in out
    assert "scan diff" in out.lower()


def test_diff_html_to_file(tmp_path, capsys):
    old = _write_scan(tmp_path / "old.json", 4)
    new = _write_scan(tmp_path / "new.json", 8)
    out_file = tmp_path / "diff.html"
    assert cli.main(["--diff", old, new, "--html", "-o", str(out_file)]) == cli.EXIT_OK
    html = out_file.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert "data.cores" in html


def test_diff_missing_file_errors(tmp_path):
    old = _write_scan(tmp_path / "old.json", 4)
    assert cli.main(["--diff", old, str(tmp_path / "nope.json")]) == cli.EXIT_COLLECTOR_ERROR
