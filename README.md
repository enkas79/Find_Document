# Find Document

Applicazione desktop (PyQt6) che risponde a domande tecniche cercando nei documenti di una cartella.
La ricerca è locale; l'architettura a sorgenti (`DocumentSource`) è pronta per aggiungere SharePoint.

## Funzionamento

1. Scansione ricorsiva della cartella ed estrazione del testo (PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, …).
2. Suddivisione in passaggi (~120 parole, con sovrapposizione) e indicizzazione BM25 con stemming italiano.
3. Per ogni domanda: passaggi ordinati per pertinenza e copertura dei termini, con la frase più probabile come risposta.
4. Il testo estratto è in cache (per data/dimensione file): le indicizzazioni successive sono rapide.

## Struttura

```
src/main.py                      avvio applicazione
src/find_document/core/          sorgenti, estrazione, analisi testo, indice, cache (nessuna dipendenza Qt)
src/find_document/updater/       verifica e download aggiornamenti da GitHub Releases
src/find_document/gui/           finestra, worker QThread, dialoghi, tema QSS
installer/find_document.nsi      installer Windows
```

## Sviluppo

```bash
pip install -r requirements-dev.txt
python src/main.py
pytest
ruff check . --fix
```

Modificando `version.txt` su `main` parte la build degli installer e la pubblicazione della release.
