"""Gestione dei temi: palette WCAG AA e caricamento del foglio di stile QSS."""

from __future__ import annotations

import sys
from pathlib import Path
from string import Template

# Contrasti verificati: testo/sfondo >= 4.5:1, testo su accento >= 4.5:1
PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#1B1D22",
        "surface": "#24272E",
        "surface_alt": "#2E323A",
        "input_bg": "#1F2228",
        "hover": "#383C46",
        "border": "#41464F",
        "text": "#E8EAED",
        "text_muted": "#A7AEB9",
        "text_disabled": "#6E7480",
        "accent": "#2F6BD8",
        "accent_hover": "#245BBF",
        "on_accent": "#FFFFFF",
        "mark_bg": "#F2C94C",
        "mark_text": "#1B1D22",
        "answer_bg": "#1E3A2C",
        "answer_border": "#3FA36B",
    },
    "light": {
        "bg": "#F3F4F6",
        "surface": "#FFFFFF",
        "surface_alt": "#ECEEF1",
        "input_bg": "#FFFFFF",
        "hover": "#E1E4E9",
        "border": "#C9CED6",
        "text": "#1A1D23",
        "text_muted": "#4F5662",
        "text_disabled": "#8A909A",
        "accent": "#1F5FCC",
        "accent_hover": "#184EA8",
        "on_accent": "#FFFFFF",
        "mark_bg": "#FFE27A",
        "mark_text": "#1A1D23",
        "answer_bg": "#E7F5EC",
        "answer_border": "#2E8B57",
    },
}

DEFAULT_THEME = "dark"


def _resources_dir() -> Path:
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir) / "find_document" / "gui" / "resources"
    return Path(__file__).resolve().parent / "resources"


def palette(theme: str) -> dict[str, str]:
    return PALETTES.get(theme, PALETTES[DEFAULT_THEME])


def load_stylesheet(theme: str) -> str:
    """Restituisce il QSS con le variabili del tema sostituite (stringa vuota se assente)."""
    try:
        template = (_resources_dir() / "styles.qss").read_text(encoding="utf-8")
    except OSError:
        return ""
    return Template(template).safe_substitute(palette(theme))
