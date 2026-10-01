"""Sorgenti di documenti: astrazione comune per cartella locale e (in futuro) SharePoint."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceDocument:
    """Metadati di un documento indipendenti dalla sorgente."""

    doc_id: str  # identificativo univoco nella sorgente (path assoluto, id SharePoint, ...)
    name: str  # nome visualizzato
    location: str  # percorso o URL apribile dall'utente
    extension: str  # estensione minuscola con punto, es. ".pdf"
    modified: float  # timestamp ultima modifica
    size: int  # dimensione in byte

    @property
    def fingerprint(self) -> str:
        """Impronta usata dalla cache per capire se il documento è cambiato."""
        return f"{self.modified:.3f}:{self.size}"


class DocumentSource(ABC):
    """Interfaccia comune a tutte le sorgenti di documenti."""

    @property
    @abstractmethod
    def source_key(self) -> str:
        """Chiave stabile della sorgente (usata per la cache)."""

    @abstractmethod
    def iter_documents(self, extensions: set[str]) -> Iterator[SourceDocument]:
        """Elenca i documenti con le estensioni supportate."""

    @abstractmethod
    def read_bytes(self, document: SourceDocument) -> bytes:
        """Restituisce il contenuto binario del documento."""


class LocalFolderSource(DocumentSource):
    """Sorgente basata su una cartella del file system (scansione ricorsiva)."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        recursive: bool = True,
        max_file_size: int = 100 * 1024 * 1024,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.recursive = recursive
        self.max_file_size = max_file_size
        self._is_cancelled = is_cancelled or (lambda: False)

    @property
    def source_key(self) -> str:
        return f"local:{self.root}"

    def iter_documents(self, extensions: set[str]) -> Iterator[SourceDocument]:
        if not self.root.is_dir():
            raise FileNotFoundError(f"Cartella non trovata: {self.root}")
        for dirpath, dirnames, filenames in os.walk(self.root, onerror=lambda _e: None):
            if self._is_cancelled():
                return
            # Esclude cartelle nascoste e di sistema
            dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "~", "$")))
            if not self.recursive:
                dirnames.clear()
            for filename in sorted(filenames):
                # Esclude file temporanei di Office (~$doc.docx) e nascosti
                if filename.startswith(("~$", ".")):
                    continue
                ext = os.path.splitext(filename)[1].lower()
                if ext not in extensions:
                    continue
                path = Path(dirpath) / filename
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if stat.st_size == 0 or stat.st_size > self.max_file_size:
                    continue
                yield SourceDocument(
                    doc_id=str(path),
                    name=filename,
                    location=str(path),
                    extension=ext,
                    modified=stat.st_mtime,
                    size=stat.st_size,
                )

    def read_bytes(self, document: SourceDocument) -> bytes:
        return Path(document.doc_id).read_bytes()
