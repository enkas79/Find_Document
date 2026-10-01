"""Test di integrazione GUI (piattaforma Qt offscreen)."""

from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from find_document.gui import main_window as mw  # noqa: E402


@pytest.fixture
def window(qtbot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from PyQt6.QtCore import QSettings

    # Impostazioni isolate e nessuna verifica di rete all'avvio
    QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path / "s"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "s"))
    monkeypatch.setattr(mw, "UPDATE_CHECK_DELAY_MS", 10**9)
    monkeypatch.setattr("find_document.core.cache.default_cache_dir", lambda: tmp_path / "cache")
    win = mw.MainWindow()
    qtbot.addWidget(win)
    return win


def test_menu_aiuto_contiene_voci_obbligatorie(window) -> None:
    menus = {a.text(): a.menu() for a in window.menuBar().actions()}
    help_actions = [a.text() for a in menus["&Aiuto"].actions() if not a.isSeparator()]
    assert help_actions == ["Guida", "Controlla aggiornamenti", "Informazioni"]


def test_flusso_indicizzazione_e_ricerca(window, qtbot, docs_folder: Path) -> None:
    window.folder_edit.setText(str(docs_folder))
    window.question_edit.setText("coppia di serraggio viti M12")
    window.start_search()  # senza indice: indicizza e poi cerca

    qtbot.waitUntil(lambda: window.results_tree.topLevelItemCount() > 0, timeout=15000)
    first = window.results_tree.topLevelItem(0)
    assert first.text(0) == "flangia.md"
    assert "85 Nm" in window.detail_browser.toPlainText()
    assert window.open_doc_button.isEnabled()


def test_cambio_tema(window) -> None:
    window.apply_theme("light")
    assert window.theme == "light"
    from PyQt6.QtWidgets import QApplication

    assert "#FFFFFF" in QApplication.instance().styleSheet()
