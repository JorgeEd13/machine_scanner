"""Default report filename — localized by the OS UI language (filename only).

When the frozen binary is double-clicked it writes an HTML report next to
itself (see :mod:`machine_scanner.cli`). A bare ``machine_inventory.html`` is
fine in English, but on a non-English desktop a localized *filename* is a small,
honest touch — so a PT-BR box yields ``inventario_de_maquina.html``.

Scope, deliberately narrow (ADR-017):

* **Filename only.** The report *content* stays English — the project's
  "English everywhere" rule plus full content i18n is a real, separate effort
  parked under ROADMAP Ideas. This map translates exactly one string.
* **Pure stdlib, offline, never raises.** Language detection is best-effort and
  falls back to English on any doubt; it must never break a scan.
"""

from __future__ import annotations

import locale
import os

# language (ISO-639-1, lower-case) -> base filename (no extension).
# Kept tiny on purpose: a handful of languages a portfolio reviewer might run
# this under, English as the universal fallback. Adding one is a one-line edit.
LOCALIZED_REPORT_NAMES = {
    "en": "machine_inventory",
    "pt": "inventario_de_maquina",
    "es": "inventario_de_equipo",
    "fr": "inventaire_machine",
    "de": "maschineninventar",
}
DEFAULT_LANG = "en"


def _lang_from_windows() -> str | None:
    """Windows UI language via ``GetUserDefaultUILanguage`` (LANGID -> code).

    ``locale.windows_locale`` maps the Windows LCID to a name like ``pt_BR``;
    we keep the leading language tag. Best-effort: any failure returns ``None``
    so the caller falls through to the cross-platform path.
    """
    try:
        import ctypes

        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
        name = locale.windows_locale.get(langid)  # e.g. "pt_BR", "en_US"
        if name:
            return name.split("_", 1)[0].lower()
    except Exception:
        return None
    return None


def _lang_from_env() -> str | None:
    """POSIX-style language from the environment (``LC_ALL`` / ``LANG`` / ...).

    A value like ``pt_BR.UTF-8`` -> ``pt``; ``C`` / ``POSIX`` -> ``None``.
    """
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        val = os.environ.get(var)
        if not val:
            continue
        # LANGUAGE may be a colon-separated priority list ("pt_BR:pt:en").
        tag = val.split(":", 1)[0]
        # Strip encoding / modifier: "pt_BR.UTF-8@euro" -> "pt_BR".
        tag = tag.split(".", 1)[0].split("@", 1)[0]
        code = tag.split("_", 1)[0].lower()
        if code and code not in ("c", "posix"):
            return code
    return None


def detect_ui_language() -> str:
    """Best-effort ISO-639-1 language code for the current user. Never raises.

    Order: Windows UI language, then the POSIX ``LANG``-family env vars, then
    Python's own locale, then the English default. Only the *language* tag is
    returned (``pt``, ``en``), not the territory.
    """
    if os.name == "nt":
        win = _lang_from_windows()
        if win:
            return win

    env = _lang_from_env()
    if env:
        return env

    try:
        # getlocale() reads the process locale; getdefaultlocale() the user's.
        for getter in (locale.getlocale, locale.getdefaultlocale):
            try:
                name = getter()[0]
            except Exception:
                name = None
            if name:
                return name.split("_", 1)[0].lower()
    except Exception:
        pass

    return DEFAULT_LANG


def report_basename(lang: str | None = None) -> str:
    """Localized base filename (no extension) for the default report.

    Unknown / unmapped languages fall back to the English name.
    """
    if lang is None:
        lang = detect_ui_language()
    return LOCALIZED_REPORT_NAMES.get(lang, LOCALIZED_REPORT_NAMES[DEFAULT_LANG])


def report_filename(lang: str | None = None) -> str:
    """Localized default report filename, e.g. ``inventario_de_maquina.html``."""
    return f"{report_basename(lang)}.html"
