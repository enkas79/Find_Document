"""Finestra principale: selezione cartella, domanda, risultati e dettaglio della risposta."""

from __future__ import annotations

import html
import re
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import APP_AUTHOR, APP_NAME
from ..core.indexer import IndexReport
from ..core.search_index import SearchIndex, SearchResult
from ..core.sources import LocalFolderSource
from ..version import get_version
from .guide_dialog import GuideDialog
from .styles import DEFAULT_THEME, load_stylesheet, palette
from .update_controller import UpdateController
from .workers import IndexWorker, SearchWorker

RESULT_ROLE = Qt.ItemDataRole.UserRole
UPDATE_CHECK_DELAY_MS = 2500


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.version = get_version()
        self.settings = QSettings(APP_AUTHOR, "FindDocument")
        self.theme = str(self.settings.value("theme", DEFAULT_THEME))

        self._index: SearchIndex | None = None
        self._indexed_folder: str | None = None
        self._last_report: IndexReport | None = None
        self._index_worker: IndexWorker | None = None
        self._search_worker: SearchWorker | None = None
        self._pending_question: str | None = None

        self.setWindowTitle(f"{APP_NAME} {self.version}")
        self.setMinimumSize(900, 600)
        self._build_ui()
        self._build_menu()
        self.apply_theme(self.theme)

        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1200, 760)

        self.updates = UpdateController(self, self.version)
        QTimer.singleShot(UPDATE_CHECK_DELAY_MS, lambda: self.updates.check(silent=True))

        last_folder = str(self.settings.value("last_folder", "") or "")
        if last_folder and Path(last_folder).is_dir():
            self.folder_edit.setText(last_folder)
            QTimer.singleShot(0, self.start_indexing)

    # --- Costruzione interfaccia ---------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 8)
        root.setSpacing(12)

        # Card sorgente documenti
        source_card = QFrame(objectName="Card")
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(16, 12, 16, 12)
        source_layout.setSpacing(8)
        source_layout.addWidget(QLabel("CARTELLA DOCUMENTI", objectName="SectionLabel"))
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self.folder_edit = QLineEdit(readOnly=True, placeholderText="Nessuna cartella selezionata")
        self.folder_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.browse_button = QPushButton("Sfoglia…")
        self.browse_button.clicked.connect(self.choose_folder)
        self.reindex_button = QPushButton("Aggiorna indice")
        self.reindex_button.clicked.connect(self.start_indexing)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self.browse_button)
        folder_row.addWidget(self.reindex_button)
        source_layout.addLayout(folder_row)
        self.index_status = QLabel("Seleziona una cartella per iniziare.", objectName="Muted")
        self.index_status.setTextFormat(Qt.TextFormat.RichText)
        self.index_status.linkActivated.connect(lambda _link: self.show_index_errors())
        source_layout.addWidget(self.index_status)
        root.addWidget(source_card)

        # Domanda
        question_row = QHBoxLayout()
        question_row.setSpacing(8)
        self.question_edit = QLineEdit(
            objectName="QuestionInput",
            placeholderText="Scrivi la tua domanda tecnica, es. «coppia di serraggio viti M12»",
        )
        self.question_edit.setClearButtonEnabled(True)
        self.question_edit.returnPressed.connect(self.start_search)
        self.search_button = QPushButton("Cerca", objectName="Primary")
        self.search_button.setMinimumWidth(112)
        self.search_button.clicked.connect(self.start_search)
        question_row.addWidget(self.question_edit, 1)
        question_row.addWidget(self.search_button)
        root.addLayout(question_row)

        # Risultati e dettaglio
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        results_panel = QWidget()
        results_layout = QVBoxLayout(results_panel)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(8)
        self.results_label = QLabel("RISULTATI", objectName="SectionLabel")
        results_layout.addWidget(self.results_label)
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["Documento", "Posizione", "Termini"])
        self.results_tree.setRootIsDecorated(False)
        self.results_tree.setUniformRowHeights(True)
        self.results_tree.setAlternatingRowColors(False)
        header = self.results_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        self.results_tree.currentItemChanged.connect(self._on_result_selected)
        self.results_tree.itemDoubleClicked.connect(lambda *_: self.open_current_document())
        results_layout.addWidget(self.results_tree, 1)
        splitter.addWidget(results_panel)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(8)
        detail_layout.addWidget(QLabel("DETTAGLIO", objectName="SectionLabel"))
        self.detail_browser = QTextBrowser()
        self.detail_browser.setOpenLinks(False)
        detail_layout.addWidget(self.detail_browser, 1)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        actions_row.addStretch(1)
        self.open_folder_button = QPushButton("Apri cartella")
        self.open_folder_button.clicked.connect(self.open_current_folder)
        self.open_doc_button = QPushButton("Apri documento", objectName="Primary")
        self.open_doc_button.clicked.connect(self.open_current_document)
        actions_row.addWidget(self.open_folder_button)
        actions_row.addWidget(self.open_doc_button)
        detail_layout.addLayout(actions_row)
        splitter.addWidget(detail_panel)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)

        # Barra di stato con progresso
        self.status_label = QLabel("Pronto")
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setVisible(False)
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self._set_detail_buttons_enabled(False)
        self._show_placeholder()
        self.question_edit.setFocus()

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        open_action = QAction("Apri cartella…", self, shortcut=QKeySequence(QKeySequence.StandardKey.Open))
        open_action.triggered.connect(self.choose_folder)
        reindex_action = QAction("Aggiorna indice", self, shortcut=QKeySequence("F5"))
        reindex_action.triggered.connect(self.start_indexing)
        quit_action = QAction("Esci", self, shortcut=QKeySequence(QKeySequence.StandardKey.Quit))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(open_action)
        file_menu.addAction(reindex_action)
        file_menu.addSeparator()
        file_menu.addAction(quit_action)

        view_menu = menu_bar.addMenu("&Visualizza")
        theme_group = QActionGroup(self)
        for key, label in (("dark", "Tema scuro"), ("light", "Tema chiaro")):
            action = QAction(label, self, checkable=True)
            action.setChecked(key == self.theme)
            action.triggered.connect(lambda _checked, k=key: self.apply_theme(k))
            theme_group.addAction(action)
            view_menu.addAction(action)

        help_menu = menu_bar.addMenu("&Aiuto")
        guide_action = QAction("Guida", self, shortcut=QKeySequence(QKeySequence.StandardKey.HelpContents))
        guide_action.triggered.connect(self.show_guide)
        update_action = QAction("Controlla aggiornamenti", self)
        update_action.triggered.connect(lambda: self.updates.check(silent=False))
        about_action = QAction("Informazioni", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(guide_action)
        help_menu.addAction(update_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)

    # --- Tema -----------------------------------------------------------------

    def apply_theme(self, theme: str) -> None:
        self.theme = theme
        self.settings.setValue("theme", theme)
        QApplication.instance().setStyleSheet(load_stylesheet(theme))
        # Ridisegna il dettaglio con i colori del nuovo tema
        current = self.results_tree.currentItem()
        if current is not None:
            self._on_result_selected(current, None)
        else:
            self._show_placeholder()

    # --- Indicizzazione -------------------------------------------------------

    def choose_folder(self) -> None:
        start = self.folder_edit.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Seleziona la cartella dei documenti", start)
        if not folder:
            return
        self.folder_edit.setText(folder)
        self.settings.setValue("last_folder", folder)
        self.start_indexing()

    def start_indexing(self) -> None:
        folder = self.folder_edit.text().strip()
        if not folder:
            self.choose_folder()
            return
        if self._index_worker is not None and self._index_worker.isRunning():
            return
        if not Path(folder).is_dir():
            QMessageBox.warning(self, "Cartella non trovata", f"La cartella non esiste:\n{folder}")
            return

        worker = IndexWorker(LocalFolderSource(folder), self)
        worker.progress.connect(self._on_index_progress)
        worker.completed.connect(lambda index, report, f=folder: self._on_index_done(f, index, report))
        worker.failed.connect(self._on_index_failed)
        worker.finished.connect(self._on_index_thread_finished)
        self._index_worker = worker

        self._set_busy(True, "Scansione della cartella…")
        self.index_status.setText("Indicizzazione in corso…")
        worker.start()

    def _on_index_progress(self, done: int, total: int, name: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(done)
        self.status_label.setText(f"Analisi {done}/{total}: {name}")

    def _on_index_done(self, folder: str, index: SearchIndex, report: IndexReport) -> None:
        self._index = index
        self._indexed_folder = folder
        self._last_report = report
        text = (
            f"{report.indexed_documents} documenti indicizzati "
            f"({report.passages} passaggi, {report.from_cache} da cache)."
        )
        if report.errors:
            text += f" <a href='errors'>{len(report.errors)} non leggibili</a>."
        if report.cancelled:
            text += " Indicizzazione interrotta."
        if report.total_documents == 0:
            text = "Nessun documento supportato trovato nella cartella."
        self.index_status.setText(text)
        self.status_label.setText("Indice pronto")

        if self._pending_question:
            question, self._pending_question = self._pending_question, None
            self.question_edit.setText(question)
            QTimer.singleShot(0, self.start_search)

    def _on_index_failed(self, message: str) -> None:
        self._pending_question = None
        self.index_status.setText("Indicizzazione non riuscita.")
        QMessageBox.critical(self, "Errore di indicizzazione", message)

    def _on_index_thread_finished(self) -> None:
        self._set_busy(False)
        if self._index_worker is not None:
            self._index_worker.deleteLater()
            self._index_worker = None

    def show_index_errors(self) -> None:
        if not self._last_report or not self._last_report.errors:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Documenti non leggibili")
        box.setText(
            f"{len(self._last_report.errors)} documenti non sono stati indicizzati "
            "(file protetti, danneggiati o senza testo, es. PDF scansionati)."
        )
        box.setDetailedText(
            "\n".join(f"{path}\n    → {msg}" for path, msg in sorted(self._last_report.errors.items()))
        )
        box.exec()

    # --- Ricerca --------------------------------------------------------------

    def start_search(self) -> None:
        question = self.question_edit.text().strip()
        if not question:
            self.question_edit.setFocus()
            return
        indexing = self._index_worker is not None and self._index_worker.isRunning()
        if self._index is None or indexing:
            # La domanda verrà eseguita al termine dell'indicizzazione
            self._pending_question = question
            if not indexing:
                self.start_indexing()
            self.status_label.setText("La ricerca partirà al termine dell'indicizzazione…")
            return
        if self._search_worker is not None and self._search_worker.isRunning():
            self._pending_question = question
            return

        worker = SearchWorker(self._index, question, parent=self)
        worker.completed.connect(self._on_search_done)
        worker.failed.connect(lambda msg: QMessageBox.warning(self, "Ricerca", msg))
        worker.finished.connect(self._on_search_thread_finished)
        self._search_worker = worker
        self.search_button.setEnabled(False)
        self.status_label.setText("Ricerca in corso…")
        worker.start()

    def _on_search_thread_finished(self) -> None:
        self.search_button.setEnabled(True)
        if self._search_worker is not None:
            self._search_worker.deleteLater()
            self._search_worker = None
        if self._pending_question:
            self._pending_question = None
            QTimer.singleShot(0, self.start_search)

    def _on_search_done(self, question: str, results: list[SearchResult]) -> None:
        self.results_tree.clear()
        for result in results:
            item = QTreeWidgetItem(
                [result.document.name, result.passage.location or "—", f"{result.coverage:.0%}"]
            )
            item.setToolTip(0, result.document.location)
            item.setData(0, RESULT_ROLE, result)
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.results_tree.addTopLevelItem(item)

        count = len(results)
        self.results_label.setText(f"RISULTATI ({count})")
        if count:
            self.results_tree.setCurrentItem(self.results_tree.topLevelItem(0))
            self.status_label.setText(f"{count} passaggi trovati per «{question}»")
        else:
            self._set_detail_buttons_enabled(False)
            self._show_placeholder(
                "Nessun passaggio pertinente trovato. Prova con termini diversi "
                "o più specifici presenti nei documenti."
            )
            self.status_label.setText("Nessun risultato")

    # --- Dettaglio ------------------------------------------------------------

    def _current_result(self) -> SearchResult | None:
        item = self.results_tree.currentItem()
        return item.data(0, RESULT_ROLE) if item is not None else None

    def _on_result_selected(self, current: QTreeWidgetItem | None, _previous) -> None:
        result: SearchResult | None = current.data(0, RESULT_ROLE) if current else None
        if result is None:
            self._set_detail_buttons_enabled(False)
            self._show_placeholder()
            return
        self._set_detail_buttons_enabled(True)
        self.detail_browser.setHtml(self._render_result(result))

    def _render_result(self, result: SearchResult) -> str:
        colors = palette(self.theme)
        words = self._index.highlight_words(result.passage.text, result.matched_terms) if self._index else []

        def highlight(text: str) -> str:
            escaped = html.escape(text)
            if not words:
                return escaped
            pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b")
            return pattern.sub(
                rf"<span style='background-color:{colors['mark_bg']};"
                rf"color:{colors['mark_text']};'>\1</span>",
                escaped,
            )

        location = f" — {html.escape(result.passage.location)}" if result.passage.location else ""
        return f"""
        <div style='color:{colors["text"]};'>
          <p style='color:{colors["text_muted"]};font-size:9pt;font-weight:600;'>RISPOSTA SUGGERITA</p>
          <table width='100%' cellpadding='12' cellspacing='0'
                 style='background-color:{colors["answer_bg"]};
                        border-left:4px solid {colors["answer_border"]};'>
            <tr><td style='font-size:11pt;'>{highlight(result.best_sentence)}</td></tr>
          </table>
          <p style='color:{colors["text_muted"]};font-size:9pt;font-weight:600;margin-top:16px;'>
            FONTE</p>
          <p><b>{html.escape(result.document.name)}</b>{location}<br>
             <span style='color:{colors["text_muted"]};'>{html.escape(result.document.location)}</span></p>
          <p style='color:{colors["text_muted"]};font-size:9pt;font-weight:600;margin-top:16px;'>
            PASSAGGIO COMPLETO</p>
          <p style='line-height:140%;'>{highlight(result.passage.text)}</p>
        </div>
        """

    def _show_placeholder(self, message: str | None = None) -> None:
        colors = palette(self.theme)
        text = message or "Seleziona una cartella, scrivi una domanda e premi <b>Cerca</b>."
        self.detail_browser.setHtml(
            f"<p style='color:{colors['text_muted']};margin-top:24px;' align='center'>{text}</p>"
        )

    def _set_detail_buttons_enabled(self, enabled: bool) -> None:
        self.open_doc_button.setEnabled(enabled)
        self.open_folder_button.setEnabled(enabled)

    def open_current_document(self) -> None:
        result = self._current_result()
        if result is not None:
            self._open_local(result.document.location)

    def open_current_folder(self) -> None:
        result = self._current_result()
        if result is not None:
            self._open_local(str(Path(result.document.location).parent))

    def _open_local(self, path: str) -> None:
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            QMessageBox.warning(self, "Apertura non riuscita", f"Impossibile aprire:\n{path}")

    # --- Menu Aiuto -----------------------------------------------------------

    def show_guide(self) -> None:
        GuideDialog(self).exec()

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            f"Informazioni su {APP_NAME}",
            f"<h3>{APP_NAME}</h3>"
            f"<p>Versione {html.escape(get_version())}</p>"
            f"<p>Autore: {APP_AUTHOR}</p>"
            "<p>Ricerca di risposte tecniche nei documenti locali.</p>",
        )

    # --- Stato e chiusura -----------------------------------------------------

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.progress_bar.setVisible(busy)
        if busy:
            self.progress_bar.setRange(0, 0)
        self.browse_button.setEnabled(not busy)
        self.reindex_button.setEnabled(not busy)
        if message:
            self.status_label.setText(message)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API Qt
        self.settings.setValue("geometry", self.saveGeometry())
        if self._index_worker is not None and self._index_worker.isRunning():
            self._index_worker.cancel()
            self._index_worker.wait(5000)
        if self._search_worker is not None and self._search_worker.isRunning():
            self._search_worker.wait(5000)
        self.updates.shutdown()
        super().closeEvent(event)
