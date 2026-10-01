from find_document.core.text_processing import (
    TextAnalyzer,
    raw_tokens,
    split_into_passages,
    split_sentences,
)


def test_raw_tokens_rimuove_accenti_e_maiuscole() -> None:
    assert raw_tokens("Perché la Pressione è ALTA?") == ["perche", "la", "pressione", "e", "alta"]


def test_analyze_filtra_stopword_e_conserva_codici() -> None:
    analyzer = TextAnalyzer()
    terms = analyzer.analyze("Qual è la coppia di serraggio delle viti M12?")
    assert "m12" in terms
    assert all(stop not in terms for stop in ("qual", "la", "di", "delle"))


def test_stemming_unifica_singolare_e_plurale() -> None:
    analyzer = TextAnalyzer()
    assert analyzer.analyze("valvola") == analyzer.analyze("valvole")


def test_passaggi_rispettano_la_dimensione_e_la_sovrapposizione() -> None:
    text = " ".join(f"Frase numero {i} con alcune parole tecniche." for i in range(100))
    passages = split_into_passages(text, "pagina 1", target_words=50, overlap_words=10)
    assert len(passages) > 1
    assert all(len(p.text.split()) <= 60 for p in passages)
    assert all(p.location == "pagina 1" for p in passages)
    # La sovrapposizione ripete l'ultima frase del passaggio precedente
    assert passages[1].text.split("\n")[0] in passages[0].text.split("\n")


def test_titoli_markdown_sono_frasi_separate() -> None:
    sentences = split_sentences("# Montaggio flangia\nLe viti M12 vanno serrate a 85 Nm. Poi verificare.")
    assert sentences == ["Montaggio flangia", "Le viti M12 vanno serrate a 85 Nm.", "Poi verificare."]


def test_frasi_lunghissime_vengono_spezzate() -> None:
    text = " ".join(["parola"] * 500)
    passages = split_into_passages(text, target_words=100, overlap_words=20)
    assert all(len(p.text.split()) <= 100 for p in passages)
    assert len(passages) >= 5


def test_testo_vuoto_non_produce_passaggi() -> None:
    assert split_into_passages("   \n\n  ") == []
