"""Lettura della versione corrente da version.txt (sorgenti o eseguibile PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path

FALLBACK_VERSION = "0.0.0"


def _candidate_paths() -> list[Path]:
    candidates = []
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        candidates.append(Path(bundle_dir) / "version.txt")
    # src/find_document/version.py -> root del progetto
    candidates.append(Path(__file__).resolve().parents[2] / "version.txt")
    return candidates


def get_version() -> str:
    """Restituisce la versione letta da version.txt, o un fallback se assente."""
    for path in _candidate_paths():
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return FALLBACK_VERSION
