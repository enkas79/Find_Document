"""Controller GUI dell'autoupdate: collega i worker di rete ai dialoghi utente."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget

from ..updater.github_updater import ReleaseInfo, launch_installer, select_asset
from .workers import DownloadWorker, UpdateCheckWorker


class UpdateController(QObject):
    """Gestisce verifica, conferma, download e avvio dell'aggiornamento."""

    def __init__(self, parent_widget: QWidget, local_version: str) -> None:
        super().__init__(parent_widget)
        self._parent = parent_widget
        self._local_version = local_version
        self._check_worker: UpdateCheckWorker | None = None
        self._download_worker: DownloadWorker | None = None
        self._progress: QProgressDialog | None = None
        self._silent = True

    def check(self, silent: bool) -> None:
        """Avvia la verifica in background. In modalità silenziosa notifica solo se c'è un update."""
        if self._check_worker is not None and self._check_worker.isRunning():
            return
        self._silent = silent
        worker = UpdateCheckWorker(self._local_version, self)
        worker.update_available.connect(self._on_update_available)
        worker.up_to_date.connect(self._on_up_to_date)
        worker.failed.connect(self._on_check_failed)
        worker.finished.connect(worker.deleteLater)
        self._check_worker = worker
        worker.start()

    def shutdown(self) -> None:
        """Interrompe in modo pulito i thread attivi alla chiusura della finestra."""
        for worker in (self._check_worker, self._download_worker):
            try:
                if worker is not None and worker.isRunning():
                    if isinstance(worker, DownloadWorker):
                        worker.cancel()
                    worker.wait(3000)
            except RuntimeError:  # oggetto Qt già distrutto
                pass

    # --- Slot ---------------------------------------------------------------

    def _on_up_to_date(self, remote_version: str) -> None:
        if not self._silent:
            QMessageBox.information(
                self._parent,
                "Aggiornamenti",
                f"Stai usando l'ultima versione disponibile ({self._local_version}).",
            )

    def _on_check_failed(self, message: str) -> None:
        if not self._silent:
            QMessageBox.warning(
                self._parent, "Aggiornamenti", f"Verifica aggiornamenti non riuscita.\n\n{message}"
            )

    def _on_update_available(self, release: ReleaseInfo) -> None:
        notes = release.notes.strip() or "Nessuna nota di rilascio."
        box = QMessageBox(self._parent)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Aggiornamento disponibile")
        box.setText(
            f"È disponibile la versione <b>{release.version}</b> "
            f"(versione installata: {self._local_version})."
        )
        box.setInformativeText("Vuoi scaricarla e installarla ora?")
        box.setDetailedText(notes)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        asset = select_asset(release)
        # Da sorgenti o senza pacchetto per questa piattaforma si apre la pagina della release
        if asset is None or not getattr(sys, "frozen", False):
            if release.html_url:
                QDesktopServices.openUrl(QUrl(release.html_url))
            return
        self._start_download(asset)

    def _start_download(self, asset) -> None:
        self._progress = QProgressDialog("Download aggiornamento…", "Annulla", 0, 100, self._parent)
        self._progress.setWindowTitle("Aggiornamento")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setValue(0)

        worker = DownloadWorker(asset, self)
        worker.progress.connect(self._on_download_progress)
        worker.completed.connect(self._on_download_completed)
        worker.failed.connect(self._on_download_failed)
        worker.finished.connect(worker.deleteLater)
        self._progress.canceled.connect(worker.cancel)
        self._download_worker = worker
        worker.start()

    def _on_download_progress(self, received: int, total: int) -> None:
        if self._progress is not None and total > 0:
            self._progress.setValue(min(100, int(received * 100 / total)))

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.reset()
            self._progress.deleteLater()
            self._progress = None

    def _on_download_failed(self, message: str) -> None:
        self._close_progress()
        QMessageBox.warning(self._parent, "Aggiornamento", f"Aggiornamento non riuscito.\n\n{message}")

    def _on_download_completed(self, path: str) -> None:
        self._close_progress()
        file_path = Path(path)
        try:
            must_quit = launch_installer(file_path)
        except OSError as exc:
            QMessageBox.critical(self._parent, "Aggiornamento", f"Impossibile avviare l'installer.\n\n{exc}")
            return
        if must_quit:
            QApplication.quit()
            return
        # macOS / Linux: si mostra il pacchetto scaricato per l'installazione manuale
        QMessageBox.information(
            self._parent,
            "Aggiornamento scaricato",
            f"Il pacchetto è stato scaricato in:\n{file_path}\n\n"
            "Chiudi l'applicazione e sostituiscila con la nuova versione.",
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path.parent)))
