"""Localized default-report filename (ADR-017) — filename only, offline.

Language detection is best-effort and platform-dependent, so the unit tests pin
the mapping (the deterministic part) and assert detection never raises and
always yields the English fallback for the unknown case.
"""

import machine_scanner.report_name as rn


def test_known_languages_map_to_localized_basenames():
    assert rn.report_basename("en") == "machine_inventory"
    assert rn.report_basename("pt") == "inventario_de_maquina"
    assert rn.report_basename("es") == "inventario_de_equipo"
    assert rn.report_basename("fr") == "inventaire_machine"
    assert rn.report_basename("de") == "maschineninventar"


def test_unknown_language_falls_back_to_english():
    assert rn.report_basename("zz") == "machine_inventory"
    assert rn.report_basename("ja") == "machine_inventory"


def test_report_filename_appends_html():
    assert rn.report_filename("pt") == "inventario_de_maquina.html"
    assert rn.report_filename("en") == "machine_inventory.html"


def test_detect_uses_explicit_lang_when_passed():
    # report_basename(None) detects; an explicit code skips detection.
    assert rn.report_filename("de") == "maschineninventar.html"


def test_detect_ui_language_never_raises_and_returns_a_code():
    code = rn.detect_ui_language()
    assert isinstance(code, str)
    assert code  # non-empty
    assert code == code.lower()


def test_env_lang_drives_detection_off_windows(monkeypatch):
    # Force the POSIX path (skip the Windows branch) and a known LANG.
    monkeypatch.setattr(rn.os, "name", "posix")
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "pt_BR.UTF-8")
    assert rn.detect_ui_language() == "pt"
    assert rn.report_filename() == "inventario_de_maquina.html"


def test_env_c_locale_is_ignored(monkeypatch):
    monkeypatch.setattr(rn.os, "name", "posix")
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "C")
    # Falls through env (C is ignored) to locale/default; must still be valid.
    code = rn.detect_ui_language()
    assert isinstance(code, str) and code
