"""LLM runtime collector — is Ollama installed? is Docker installed?

Presence only, and deliberately so. This reports **what is on disk**, never
whether it is running or healthy: that is a different question asked at a
different moment, and answering it here would mean starting a service or
opening a socket on a machine whose owner has not agreed to either.

Detection is `PATH` first (`shutil.which`), then the handful of well-known
install locations per OS — because a freshly installed Ollama on Windows does
not reach `PATH` until the user opens a new terminal, and reporting "not
installed" for a machine that has it would inflate the disk estimate that
depends on this answer.

**Nothing is executed.** `ollama --version` contacts the local server and can
hang when it is installed but stopped; `docker --version` is cheap but sets the
precedent. A file existing is enough for the question being asked.
"""

from __future__ import annotations

import os
import shutil

from ..core.models import Section, Status
from ..core.platform import current_os
from ..core.registry import register

# Approximate installed footprint, used to raise the free-disk requirement when
# a prerequisite is missing. Conservative and OS-dependent: Ollama ships GPU
# runners that dominate its size, and Docker Desktop (Windows/macOS) is a VM
# stack where Linux installs only the engine.
INSTALL_SIZE_GB: dict[str, dict[str, float]] = {
    "ollama": {"windows": 2.0, "macos": 2.0, "linux": 2.0, "other": 2.0},
    "docker": {"windows": 4.0, "macos": 4.0, "linux": 1.0, "other": 4.0},
}

_OLLAMA_PATHS = {
    "windows": [
        r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",
        r"%PROGRAMFILES%\Ollama\ollama.exe",
    ],
    "macos": ["/Applications/Ollama.app", "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama"],
    "linux": ["/usr/local/bin/ollama", "/usr/bin/ollama", "/opt/ollama/ollama"],
}

_DOCKER_PATHS = {
    "windows": [
        r"%PROGRAMFILES%\Docker\Docker\Docker Desktop.exe",
        r"%PROGRAMFILES%\Docker\Docker\resources\bin\docker.exe",
    ],
    "macos": ["/Applications/Docker.app", "/usr/local/bin/docker", "/opt/homebrew/bin/docker"],
    "linux": ["/usr/bin/docker", "/usr/local/bin/docker", "/snap/bin/docker"],
}


def _first_existing(paths: list[str]) -> str | None:
    """The first path that exists, with Windows environment variables expanded."""
    for raw in paths:
        path = os.path.expandvars(os.path.expanduser(raw))
        # An unexpanded %VAR% means the variable is unset — skip rather than
        # stat a literal path containing a percent sign.
        if "%" in path:
            continue
        if os.path.exists(path):
            return path
    return None


def _detect(command: str, known: dict[str, list[str]], system: str) -> dict:
    """Locate a tool by PATH, then by well-known install location."""
    found = shutil.which(command)
    if found:
        return {"installed": True, "path": found, "found_via": "PATH"}

    path = _first_existing(known.get(system, []))
    if path:
        return {"installed": True, "path": path, "found_via": "install location"}

    return {"installed": False, "path": None, "found_via": None}


def install_size_gb(tool: str, system: str | None = None) -> float:
    """Approximate disk needed to install ``tool`` on this OS."""
    return INSTALL_SIZE_GB[tool].get(system or current_os(), INSTALL_SIZE_GB[tool]["other"])


@register("llm_runtime")
def collect() -> Section:
    system = current_os()
    ollama = _detect("ollama", _OLLAMA_PATHS, system)
    docker = _detect("docker", _DOCKER_PATHS, system)

    data = {"ollama": ollama, "docker": docker}
    notes = ["reports presence on disk only — not whether the service is running"]

    missing = [name for name, info in (("Ollama", ollama), ("Docker", docker)) if not info["installed"]]
    if missing:
        notes.append(f"not installed: {', '.join(missing)}")

    # Always OK, including when both are absent — unlike `battery`, where an
    # absent battery means there is nothing to report, "not installed" *is* the
    # report, and it is the answer that drives the disk estimate. Downgrading it
    # would say "could not determine", which is the opposite of what happened.
    return Section("llm_runtime", "LLM Runtime", Status.OK, data, notes)
