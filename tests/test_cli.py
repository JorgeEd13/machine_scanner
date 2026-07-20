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


# --- report mode (the double-click / --report experience, ADR-017) ----------


def test_report_flag_writes_html_and_opens(monkeypatch, tmp_path):
    _stub_scan(monkeypatch, Section("cpu", "CPU", Status.OK, {"cores_logical": 4}))
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda uri: opened.append(uri) or True)
    out_file = tmp_path / "r.html"
    assert cli.main(["--report", "-o", str(out_file)]) == cli.EXIT_OK
    html = out_file.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert len(opened) == 1  # browser open attempted exactly once


def test_report_default_filename_is_localized(monkeypatch, tmp_path):
    _stub_scan(monkeypatch, Section("cpu", "CPU", Status.OK, {"cores_logical": 4}))
    monkeypatch.setattr(cli.webbrowser, "open", lambda uri: True)
    monkeypatch.setattr(cli, "report_filename", lambda: "inventario_de_maquina.html")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--report"]) == cli.EXIT_OK
    assert (tmp_path / "inventario_de_maquina.html").exists()


def test_frozen_no_args_triggers_report(monkeypatch, tmp_path):
    _stub_scan(monkeypatch, Section("cpu", "CPU", Status.OK, {"cores_logical": 4}))
    monkeypatch.setattr(cli, "_is_frozen", lambda: True)
    monkeypatch.setattr(cli.webbrowser, "open", lambda uri: True)
    monkeypatch.setattr(cli, "report_filename", lambda: "machine_inventory.html")
    monkeypatch.chdir(tmp_path)
    assert cli.main([]) == cli.EXIT_OK  # no args + frozen -> report mode
    assert (tmp_path / "machine_inventory.html").exists()


def test_frozen_with_args_keeps_normal_cli(monkeypatch, capsys):
    # A terminal run of the binary with a flag must behave like the script.
    _stub_scan(monkeypatch, Section("cpu", "CPU", Status.OK, {"cores_logical": 4}))
    monkeypatch.setattr(cli, "_is_frozen", lambda: True)
    cli.main(["--json"])
    assert '"cores_logical": 4' in capsys.readouterr().out


def test_non_frozen_no_args_stays_text(monkeypatch, capsys):
    # The normal CLI default (text to stdout) is untouched when not frozen.
    _stub_scan(monkeypatch, Section("cpu", "CPU", Status.OK, {"cores_logical": 4}))
    monkeypatch.setattr(cli, "_is_frozen", lambda: False)
    assert cli.main([]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "CPU" in out
    assert "<!doctype html>" not in out  # text, not the report-mode HTML


# --------------------------------------------------------------------------- #
# advisor wiring (ROADMAP F1) — the fit section rides along with a normal scan
# --------------------------------------------------------------------------- #

_MEMORY = Section("memory", "Memory", Status.OK, {"total_gb": 16.0})


def test_scan_includes_the_fit_section(monkeypatch, capsys):
    _stub_scan(monkeypatch, _MEMORY)
    cli.main(["--json"])
    assert '"ollama_fit"' in capsys.readouterr().out


def test_only_filter_excludes_the_fit_section(monkeypatch, capsys):
    _stub_scan(monkeypatch, _MEMORY)
    cli.main(["--only", "memory", "--json"])
    assert "ollama_fit" not in capsys.readouterr().out


def test_ollama_flag_prints_just_the_verdict(monkeypatch, capsys):
    _stub_scan(monkeypatch, _MEMORY)
    assert cli.main(["--ollama"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Verdict" in out
    assert "Memory" not in out.split("Verdict")[0]  # the full scan is not dumped


def test_ollama_flag_still_reports_a_collector_bug(monkeypatch, capsys):
    _stub_scan(monkeypatch, _MEMORY, Section("boom", "BOOM", Status.ERROR, notes=["kaboom"]))
    assert cli.main(["--ollama"]) == cli.EXIT_COLLECTOR_ERROR
