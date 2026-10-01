"""Dialogo con la guida all'uso dell'applicazione."""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget

from ..core.extractors import supported_extensions

GUIDE_HTML = """
<h2>Come funziona Find Document</h2>
<p>L'applicazione analizza i documenti di una cartella e cerca i passaggi che meglio
rispondono alla tua domanda tecnica. La ricerca avviene <b>interamente in locale</b>:
nessun documento viene inviato in rete.</p>

<h3>1. Scegli la cartella</h3>
<p>Premi <b>Sfoglia…</b> (o <i>File → Apri cartella</i>) e seleziona la cartella con la
documentazione. Le sottocartelle sono incluse. L'indicizzazione parte automaticamente.</p>

<h3>2. Fai la domanda</h3>
<p>Scrivi la domanda in linguaggio naturale, ad esempio:<br>
<i>«Qual è la coppia di serraggio delle viti M12 della flangia?»</i><br>
e premi <b>Invio</b> o <b>Cerca</b>. Parole come «qual», «della», «è» vengono ignorate;
contano i termini tecnici (coppia, serraggio, viti, M12, flangia).</p>

<h3>3. Leggi i risultati</h3>
<ul>
<li><b>Risposta suggerita</b>: la frase del passaggio che contiene più termini della domanda.</li>
<li><b>Termini</b>: percentuale dei termini della domanda presenti nel passaggio.</li>
<li><b>Posizione</b>: pagina, foglio o slide in cui si trova il passaggio.</li>
<li>Doppio clic su un risultato (o <b>Apri documento</b>) per aprire il file.</li>
</ul>

<h3>Suggerimenti</h3>
<ul>
<li>Usa i termini presenti nei documenti (sigle, codici, nomi di componenti).</li>
<li>Domande brevi e specifiche danno risultati più precisi.</li>
<li>I file già analizzati sono in cache: le indicizzazioni successive sono rapide.
Usa <i>File → Aggiorna indice</i> dopo aver modificato i documenti.</li>
<li>I PDF scansionati (solo immagini) non contengono testo e vengono segnalati come
non leggibili.</li>
</ul>

<h3>Formati supportati</h3>
<p>{formats}</p>

<h3>Limiti attuali</h3>
<p>La ricerca è lessicale (con riconoscimento delle varianti delle parole, es.
«valvola/valvole»): trova i passaggi pertinenti ma non riformula la risposta.
Sinonimi non presenti nel testo non vengono riconosciuti.</p>
"""


class GuideDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Guida")
        self.resize(640, 560)

        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(True)
        formats = ", ".join(sorted(supported_extensions()))
        browser.setHtml(GUIDE_HTML.replace("{formats}", formats))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(browser)
        layout.addWidget(buttons)
