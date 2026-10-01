"""Indice di ricerca a passaggi basato su BM25, con estrazione della frase-risposta."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .sources import SourceDocument
from .text_processing import Passage, TextAnalyzer


@dataclass(frozen=True)
class IndexedPassage:
    document: SourceDocument
    passage: Passage


@dataclass(frozen=True)
class SearchResult:
    """Risultato di ricerca: passaggio pertinente e frase che meglio risponde alla domanda."""

    document: SourceDocument
    passage: Passage
    score: float
    coverage: float  # frazione dei termini della domanda presenti nel passaggio (0..1)
    best_sentence: str
    matched_terms: frozenset[str] = field(default_factory=frozenset)


_SENTENCE_RE = re.compile(r"(?<=[.!?;:])\s+|\n+")


class SearchIndex:
    """Indice invertito BM25 su passaggi di documenti."""

    def __init__(self, analyzer: TextAnalyzer | None = None, k1: float = 1.5, b: float = 0.75):
        self.analyzer = analyzer or TextAnalyzer()
        self.k1 = k1
        self.b = b
        self._passages: list[IndexedPassage] = []
        self._lengths: list[int] = []
        self._postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._name_terms: list[set[str]] = []
        self._avg_len = 0.0

    def __len__(self) -> int:
        return len(self._passages)

    @property
    def document_count(self) -> int:
        return len({p.document.doc_id for p in self._passages})

    def add(self, document: SourceDocument, passages: list[Passage]) -> None:
        name_terms = set(self.analyzer.analyze(document.name.rsplit(".", 1)[0]))
        for passage in passages:
            terms = self.analyzer.analyze(passage.text)
            if not terms:
                continue
            idx = len(self._passages)
            self._passages.append(IndexedPassage(document, passage))
            self._lengths.append(len(terms))
            self._name_terms.append(name_terms)
            for term, freq in Counter(terms).items():
                self._postings[term].append((idx, freq))
        total = sum(self._lengths)
        self._avg_len = total / len(self._lengths) if self._lengths else 0.0

    def _idf(self, term: str) -> float:
        n = len(self._passages)
        df = len(self._postings.get(term, ()))
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(
        self,
        question: str,
        limit: int = 20,
        max_per_document: int = 3,
        min_coverage: float = 0.0,
    ) -> list[SearchResult]:
        """Cerca i passaggi più pertinenti alla domanda."""
        query_terms = list(dict.fromkeys(self.analyzer.analyze(question)))
        if not query_terms or not self._passages:
            return []

        scores: dict[int, float] = defaultdict(float)
        matches: dict[int, set[str]] = defaultdict(set)
        for term in query_terms:
            postings = self._postings.get(term)
            if not postings:
                continue
            idf = self._idf(term)
            for idx, freq in postings:
                norm = self.k1 * (1 - self.b + self.b * self._lengths[idx] / self._avg_len)
                scores[idx] += idf * freq * (self.k1 + 1) / (freq + norm)
                matches[idx].add(term)

        total_terms = len(query_terms)
        ranked: list[tuple[float, int, float]] = []
        for idx, base in scores.items():
            coverage = len(matches[idx]) / total_terms
            if coverage < min_coverage:
                continue
            # Premia i passaggi che coprono più termini della domanda e i file con nome pertinente
            name_bonus = 0.15 * len(self._name_terms[idx] & set(query_terms)) / total_terms
            ranked.append((base * (0.5 + coverage) * (1 + name_bonus), idx, coverage))
        ranked.sort(key=lambda item: item[0], reverse=True)

        results: list[SearchResult] = []
        per_document: Counter[str] = Counter()
        for score, idx, coverage in ranked:
            item = self._passages[idx]
            if per_document[item.document.doc_id] >= max_per_document:
                continue
            per_document[item.document.doc_id] += 1
            results.append(
                SearchResult(
                    document=item.document,
                    passage=item.passage,
                    score=score,
                    coverage=coverage,
                    best_sentence=self.best_sentence(item.passage.text, query_terms),
                    matched_terms=frozenset(matches[idx]),
                )
            )
            if len(results) >= limit:
                break
        return results

    def best_sentence(self, text: str, query_terms: list[str]) -> str:
        """Seleziona la frase del passaggio che contiene più termini della domanda."""
        wanted = set(query_terms)
        best, best_score = "", -1.0
        for sentence in _SENTENCE_RE.split(text):
            sentence = sentence.strip()
            if len(sentence) < 3:
                continue
            terms = self.analyzer.analyze(sentence)
            if not terms:
                continue
            hits = wanted.intersection(terms)
            # Copertura dei termini con lieve penalità per frasi molto lunghe
            score = len(hits) + len(hits) / (1 + math.log(1 + len(terms)))
            if score > best_score:
                best, best_score = sentence, score
        return best or text[:300]

    def highlight_words(self, text: str, matched_terms: frozenset[str]) -> list[str]:
        """Parole originali del testo che corrispondono ai termini trovati (per l'evidenziazione)."""
        words = set(re.findall(r"\w+", text))
        return sorted(
            (w for w in words if any(t in matched_terms for t in self.analyzer.analyze(w))),
            key=len,
            reverse=True,
        )
