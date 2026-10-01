"""Worker QThread: nessuna operazione di I/O o rete gira nel thread della GUI."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from ..core.indexer import Indexer
from ..core.search_index import SearchIndex
from ..core.sources import DocumentSource
from ..updater.github_updater import (
    ReleaseAsset,
    UpdateError,
    download_asset,
    fetch_latest_release,
    is_newer,
)

logger = logging.getLogger(__name__)


class CancellableThread(QThread):
    """QThread con flag di annullamento cooperativo."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled


class IndexWorker(CancellableThread):
    progress = pyqtSignal(int, int, str)
    completed = pyqtSignal(object, object)  # SearchIndex, IndexReport
    failed = pyqtSignal(str)

    def __init__(self, source: DocumentSource, parent=None) -> None:
        super().__init__(parent)
        self._source = source

    def run(self) -> None:
        try:
            indexer = Indexer(self._source)
            index, report = indexer.build(
                progress=lambda done, total, name: self.progress.emit(done, total, name),
                is_cancelled=self.is_cancelled,
            )
        except Exception as exc:  # noqa: BLE001 - qualunque errore va mostrato, mai un crash
            logger.exception("Indicizzazione fallita")
            self.failed.emit(str(exc))
            return
        self.completed.emit(index, report)


class SearchWorker(QThread):
    completed = pyqtSignal(str, list)  # domanda, risultati
    failed = pyqtSignal(str)

    def __init__(self, index: SearchIndex, question: str, limit: int = 30, parent=None) -> None:
        super().__init__(parent)
        self._index = index
        self._question = question
        self._limit = limit

    def run(self) -> None:
        try:
            results = self._index.search(self._question, limit=self._limit)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ricerca fallita")
            self.failed.emit(str(exc))
            return
        self.completed.emit(self._question, results)


class UpdateCheckWorker(QThread):
    update_available = pyqtSignal(object)  # ReleaseInfo
    up_to_date = pyqtSignal(str)  # versione remota
    failed = pyqtSignal(str)

    def __init__(self, local_version: str, parent=None) -> None:
        super().__init__(parent)
        self._local_version = local_version

    def run(self) -> None:
        try:
            release = fetch_latest_release()
        except UpdateError as exc:
            self.failed.emit(str(exc))
            return
        if is_newer(release.version, self._local_version):
            self.update_available.emit(release)
        else:
            self.up_to_date.emit(release.version)


class DownloadWorker(CancellableThread):
    progress = pyqtSignal(int, int)
    completed = pyqtSignal(str)  # percorso del file scaricato
    failed = pyqtSignal(str)

    def __init__(self, asset: ReleaseAsset, parent=None) -> None:
        super().__init__(parent)
        self._asset = asset

    def run(self) -> None:
        try:
            path: Path = download_asset(
                self._asset,
                progress=lambda done, total: self.progress.emit(done, total),
                is_cancelled=self.is_cancelled,
            )
        except UpdateError as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(str(path))
