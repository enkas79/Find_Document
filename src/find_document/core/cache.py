"""Cache persistente del testo estratto, per evitare di rielaborare file invariati."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .text_processing import Passage

logger = logging.getLogger(__name__)

CACHE_FORMAT_VERSION = 1


@dataclass
class CachedDocument:
    fingerprint: str
    passages: list[Passage] = field(default_factory=list)
    error: str | None = None


def default_cache_dir() -> Path:
    """Cartella dati utente specifica per piattaforma."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":  # pragma: no cover - dipende dalla piattaforma
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "FindDocument"


class ExtractionCache:
    """Cache su disco (JSON compresso) associata a una singola sorgente."""

    def __init__(self, source_key: str, cache_dir: Path | None = None) -> None:
        digest = hashlib.sha1(source_key.encode("utf-8")).hexdigest()[:16]
        self.path = (cache_dir or default_cache_dir()) / f"index_{digest}.json.gz"
        self.source_key = source_key
        self._entries: dict[str, CachedDocument] = {}

    def load(self) -> None:
        self._entries = {}
        if not self.path.exists():
            return
        try:
            with gzip.open(self.path, "rt", encoding="utf-8") as fh:
                raw = json.load(fh)
            if raw.get("version") != CACHE_FORMAT_VERSION or raw.get("source") != self.source_key:
                return
            for doc_id, entry in raw.get("documents", {}).items():
                self._entries[doc_id] = CachedDocument(
                    fingerprint=entry["fp"],
                    passages=[Passage(text, loc) for text, loc in entry.get("passages", [])],
                    error=entry.get("error"),
                )
        except (OSError, ValueError, KeyError, TypeError):
            # Cache corrotta: si riparte da zero senza bloccare l'utente
            logger.warning("Cache illeggibile, verrà ricostruita: %s", self.path, exc_info=True)
            self._entries = {}

    def save(self) -> None:
        payload = {
            "version": CACHE_FORMAT_VERSION,
            "source": self.source_key,
            "documents": {
                doc_id: {
                    "fp": entry.fingerprint,
                    "passages": [[p.text, p.location] for p in entry.passages],
                    "error": entry.error,
                }
                for doc_id, entry in self._entries.items()
            },
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.path.with_suffix(".tmp")
            with gzip.open(tmp_path, "wt", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            os.replace(tmp_path, self.path)
        except OSError:
            logger.warning("Impossibile salvare la cache: %s", self.path, exc_info=True)

    def get(self, doc_id: str, fingerprint: str) -> CachedDocument | None:
        entry = self._entries.get(doc_id)
        if entry is not None and entry.fingerprint == fingerprint:
            return entry
        return None

    def put(self, doc_id: str, entry: CachedDocument) -> None:
        self._entries[doc_id] = entry

    def retain_only(self, doc_ids: set[str]) -> None:
        """Rimuove le voci dei documenti non più presenti nella sorgente."""
        self._entries = {k: v for k, v in self._entries.items() if k in doc_ids}
