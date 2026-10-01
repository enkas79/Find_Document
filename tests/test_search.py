from pathlib import Path

from find_document.core.extractors import extract_sections, supported_extensions
from find_document.core.indexer import Indexer
from find_document.core.search_index import SearchIndex
from find_document.core.sources import LocalFolderSource, SourceDocument
from find_document.core.text_processing import Passage


def _build(folder: Path, cache_dir: Path):
    return Indexer(LocalFolderSource(folder), cache_dir=cache_dir).build()


def test_sorgente_locale_ignora_file_temporanei_e_non_supportati(docs_folder: Path) -> None:
    names = {d.name for d in LocalFolderSource(docs_folder).iter_documents(supported_extensions())}
    assert names == {"pompa.txt", "flangia.md", "motore.docx", "valvole.xlsx", "corrotto.pdf"}


def test_sorgente_inesistente_solleva_errore(tmp_path: Path) -> None:
    source = LocalFolderSource(tmp_path / "manca")
    try:
        list(source.iter_documents({".txt"}))
    except FileNotFoundError:
        return
    raise AssertionError("FileNotFoundError atteso")


def test_domanda_trova_la_risposta_corretta(docs_folder: Path, tmp_path: Path) -> None:
    index, report = _build(docs_folder, tmp_path / "cache")
    assert report.indexed_documents == 4
    assert "corrotto.pdf" in "".join(report.errors)

    results = index.search("Qual è la coppia di serraggio delle viti M12 della flangia?")
    assert results[0].document.name == "flangia.md"
    assert "85 Nm" in results[0].best_sentence


def test_ricerca_in_docx_xlsx_con_varianti_morfologiche(docs_folder: Path, tmp_path: Path) -> None:
    index, _ = _build(docs_folder, tmp_path / "cache")
    assert index.search("tensione alimentazione motore")[0].document.name == "motore.docx"
    top = index.search("valvole a sfera inox")[0]
    assert top.document.name == "valvole.xlsx"
    assert top.passage.location == "foglio Valvole"


def test_pressione_massima_pompa(docs_folder: Path, tmp_path: Path) -> None:
    index, _ = _build(docs_folder, tmp_path / "cache")
    result = index.search("pressione massima della pompa")[0]
    assert result.document.name == "pompa.txt"
    assert "16 bar" in result.best_sentence
    assert result.coverage == 1.0


def test_domanda_senza_termini_utili_non_restituisce_nulla(docs_folder: Path, tmp_path: Path) -> None:
    index, _ = _build(docs_folder, tmp_path / "cache")
    assert index.search("che cosa è?") == []
    assert index.search("zzzinesistente") == []


def test_cache_riutilizza_documenti_invariati(docs_folder: Path, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    _, first = _build(docs_folder, cache_dir)
    assert first.from_cache == 0
    _, second = _build(docs_folder, cache_dir)
    assert second.from_cache == first.total_documents

    # Un file modificato viene rielaborato
    target = docs_folder / "pompa.txt"
    target.write_text("Nuovo contenuto: portata nominale 30 m3/h.", encoding="utf-8")
    index, third = _build(docs_folder, cache_dir)
    assert third.from_cache == first.total_documents - 1
    assert index.search("portata nominale")[0].document.name == "pompa.txt"


def test_annullamento_interrompe_indicizzazione(docs_folder: Path, tmp_path: Path) -> None:
    _, report = Indexer(LocalFolderSource(docs_folder), cache_dir=tmp_path / "c").build(
        is_cancelled=lambda: True
    )
    assert report.cancelled
    assert report.indexed_documents == 0


def test_limite_risultati_per_documento() -> None:
    doc = SourceDocument("id", "manuale.txt", "/x/manuale.txt", ".txt", 0.0, 1)
    index = SearchIndex()
    index.add(doc, [Passage(f"Il filtro olio numero {i} va sostituito.", "") for i in range(10)])
    assert len(index.search("filtro olio", max_per_document=2)) == 2


def test_estrazione_csv_e_formato_non_supportato() -> None:
    sections = extract_sections(b"codice;valore\nP1;16 bar\n", ".csv")
    assert "P1 | 16 bar" in sections[0].text
    try:
        extract_sections(b"x", ".exe")
    except Exception as exc:  # noqa: BLE001
        assert "non supportato" in str(exc)
    else:
        raise AssertionError("errore atteso")


def test_highlight_words_restituisce_parole_originali() -> None:
    index = SearchIndex()
    terms = frozenset(index.analyzer.analyze("valvole"))
    assert index.highlight_words("La Valvola principale e le valvole secondarie", terms) == [
        "valvole",
        "Valvola",
    ] or set(index.highlight_words("La Valvola principale e le valvole secondarie", terms)) == {
        "valvole",
        "Valvola",
    }
