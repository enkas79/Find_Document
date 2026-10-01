"""Normalizzazione del testo: tokenizzazione, stopword, stemming e suddivisione in passaggi."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

try:
    import snowballstemmer
except ImportError:  # pragma: no cover - dipendenza opzionale
    snowballstemmer = None

# Token: parole alfanumeriche, incluse sigle tecniche come "M12", "IP67", "4-20mA" (spezzate su "-")
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?")

_STOPWORDS_IT = set(
    """
    a ad al allo ai agli all agl alla alle con col coi da dal dallo dai dagli dall dagl dalla
    dalle di del dello dei degli dell degl della delle in nel nello nei negli nell negl nella
    nelle su sul sullo sui sugli sull sugl sulla sulle per tra fra il lo la i gli le l un uno
    una e ed o od ma se che chi cui non come dove quando quale quali quanto quanti quanta quante
    cosa perche anche piu sono sei siamo siete essere era erano stato stata stati state ho hai
    ha abbiamo avete hanno avere questo questa questi queste quello quella quelli quelle mi ti
    ci vi si ne io tu lui lei noi voi loro mio mia suo sua nostro vostro posso puo possono deve
    devo devono fare fa viene vengono c qual va vanno ogni tutto tutti tutta tutte solo gia
    molto
    """.split()
)

_STOPWORDS_EN = set(
    """
    a an the and or but if of to in on at by for with from as is are was were be been being it
    its this that these those what which who whom how why when where do does did can could
    should would will shall may might must have has had not no i you he she we they my your our
    their there than then so about into any all
    """.split()
)

STOPWORDS: frozenset[str] = frozenset(_STOPWORDS_IT | _STOPWORDS_EN)


def strip_accents(text: str) -> str:
    """Rimuove gli accenti (es. 'perché' -> 'perche')."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def raw_tokens(text: str) -> list[str]:
    """Tokenizza il testo in minuscolo senza accenti, senza filtrare stopword."""
    return _TOKEN_RE.findall(strip_accents(text.lower()))


class TextAnalyzer:
    """Pipeline di analisi: tokenizzazione -> stopword -> stemming."""

    def __init__(self, language: str = "italian") -> None:
        self.language = language
        self._stemmer = self._build_stemmer(language)

    @staticmethod
    def _build_stemmer(language: str):
        if snowballstemmer is None:
            return None
        try:
            return snowballstemmer.stemmer(language)
        except KeyError:
            return None

    def stem(self, token: str) -> str:
        # I token numerici o alfanumerici (codici, sigle) non vengono stemmati
        if self._stemmer is None or not token.isalpha():
            return token
        return self._stem_cached(token)

    @lru_cache(maxsize=65536)  # noqa: B019 - istanza longeva, cache voluta
    def _stem_cached(self, token: str) -> str:
        return self._stemmer.stemWord(token)

    def analyze(self, text: str) -> list[str]:
        """Restituisce i termini indicizzabili del testo."""
        return [
            self.stem(tok)
            for tok in raw_tokens(text)
            if tok not in STOPWORDS and (len(tok) > 1 or tok.isdigit())
        ]


@dataclass(frozen=True)
class Passage:
    """Porzione di documento indicizzata singolarmente."""

    text: str
    location: str  # es. "pagina 3", "foglio Dati", "slide 4"


# Confini di frase: punteggiatura forte, paragrafi vuoti, righe di titolo Markdown
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|\n\s*\n|\n(?=[ \t]*#)")
_HEADING_MARK_RE = re.compile(r"^#{1,6}\s*")


def split_sentences(text: str) -> list[str]:
    """Divide il testo in frasi con spaziatura normalizzata (i titoli Markdown restano frasi a sé)."""
    sentences = []
    for chunk in _SENTENCE_SPLIT_RE.split(text):
        for line in _split_heading_lines(chunk):
            sentence = " ".join(_HEADING_MARK_RE.sub("", line.strip()).split())
            if sentence:
                sentences.append(sentence)
    return sentences


def _split_heading_lines(chunk: str) -> list[str]:
    # Un titolo "# ..." seguito da testo sulla riga successiva viene separato
    lines = chunk.split("\n")
    if len(lines) > 1 and lines[0].lstrip().startswith("#"):
        return [lines[0], "\n".join(lines[1:])]
    return [chunk]


def split_into_passages(
    text: str,
    location: str = "",
    target_words: int = 120,
    overlap_words: int = 30,
) -> list[Passage]:
    """Divide il testo in passaggi di circa `target_words` parole, rispettando le frasi.

    Le frasi di un passaggio sono separate da "\\n". Una sovrapposizione di circa
    `overlap_words` parole (frasi intere) evita di perdere risposte a cavallo dei confini.
    """
    passages: list[Passage] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        if current:
            passages.append(Passage("\n".join(current), location))

    for sentence in split_sentences(text):
        words = sentence.split()
        # Frasi molto lunghe (es. tabelle senza punteggiatura) vengono spezzate a forza
        if len(words) > target_words:
            flush()
            current, current_len = [], 0
            step = max(1, target_words - overlap_words)
            for start in range(0, len(words), step):
                piece = words[start : start + target_words]
                passages.append(Passage(" ".join(piece), location))
                if start + target_words >= len(words):
                    break
            continue
        if current and current_len + len(words) > target_words:
            flush()
            # Sovrapposizione: si conservano le ultime frasi fino a ~overlap_words parole
            tail: list[str] = []
            tail_len = 0
            for previous in reversed(current):
                previous_len = len(previous.split())
                if tail_len + previous_len > overlap_words:
                    break
                tail.insert(0, previous)
                tail_len += previous_len
            current, current_len = tail, tail_len
        current.append(sentence)
        current_len += len(words)

    flush()
    return passages
