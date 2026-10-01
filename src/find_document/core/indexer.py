"""Orchestrazione: sorgente -> cache -> estrazione -> indice di ricerca."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .cache import CachedDocument, ExtractionCache
from .extractors import ExtractionError, extract_sections, supported_extensions
from .search_index import SearchIndex
from .sources import DocumentSource
from .text_processing import TextAnalyzer, split_into_passages

logger = logging.getLogger(__name__)

# (documenti elaborati, totale, nome file corrente)
ProgressCallback = Callable[[int, int, str], None]


@dataclass
class IndexReport:
    """Riepilogo dell'indicizzazione."""

    total_documents: int = 0
    indexed_documents: int = 0
    from_cache: int = 0
    passages: int = 0
    errors: dict[str, str] = field(default_factory=dict)  # location -> messaggio
    cancelled: bool = False


class Indexer:
    """Costruisce un SearchIndex a partire da una DocumentSource."""

    def __init__(
        self,
        source: DocumentSource,
        analyzer: TextAnalyzer | None = None,
        cache_dir: Path | None = None,
        use_cache: bool = True,
    ) -> None:
        self.source = source
        self.analyzer = analyzer or TextAnalyzer()
        self.cache = ExtractionCache(source.source_key, cache_dir) if use_cache else None

    def build(
        self,
        progress: ProgressCallback | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> tuple[SearchIndex, IndexReport]:
        is_cancelled = is_cancelled or (lambda: False)
        report = IndexReport()
        index = SearchIndex(self.analyzer)

        if self.cache is not None:
            self.cache.load()

        documents = list(self.source.iter_documents(supported_extensions()))
        report.total_documents = len(documents)

        for position, document in enumerate(documents, start=1):
            if is_cancelled():
                report.cancelled = True
                break
            if progress is not None:
                progress(position, len(documents), document.name)

            entry = self.cache.get(document.doc_id, document.fingerprint) if self.cache else None
            if entry is not None:
                report.from_cache += 1
            else:
                entry = self._extract(document)
                if self.cache is not None:
                    self.cache.put(document.doc_id, entry)

            if entry.error:
                report.errors[document.location] = entry.error
                continue
            index.add(document, entry.passages)
            report.indexed_documents += 1
            report.passages += len(entry.passages)

        if self.cache is not None and not report.cancelled:
            self.cache.retain_only({d.doc_id for d in documents})
            self.cache.save()
        return index, report

    def _extract(self, document) -> CachedDocument:
        try:
            data = self.source.read_bytes(document)
            sections = extract_sections(data, document.extension)
        except (OSError, ExtractionError) as exc:
            logger.info("Estrazione fallita per %s: %s", document.location, exc)
            return CachedDocument(document.fingerprint, error=str(exc))
        passages = []
        for section in sections:
            passages.extend(split_into_passages(section.text, section.location))
        if not passages:
            return CachedDocument(document.fingerprint, error="Nessun testo estraibile")
        return CachedDocument(document.fingerprint, passages)
