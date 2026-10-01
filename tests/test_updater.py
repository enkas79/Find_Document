import io
import json
from pathlib import Path

import pytest

from find_document.updater import github_updater as gu
from find_document.version import get_version

RELEASE_PAYLOAD = {
    "tag_name": "v1.2.0",
    "body": "Novità",
    "html_url": "https://github.com/enkas79/Find_Document/releases/tag/v1.2.0",
    "assets": [
        {"name": "FindDocument-Setup-1.2.0.exe", "browser_download_url": "https://x/setup.exe", "size": 5},
        {"name": "FindDocument-1.2.0-macos.zip", "browser_download_url": "https://x/mac.zip", "size": 5},
        {"name": "FindDocument-1.2.0-linux.tar.gz", "browser_download_url": "https://x/l.tgz", "size": 5},
    ],
}


@pytest.mark.parametrize(
    ("remote", "local", "expected"),
    [
        ("v1.0.1", "1.0.0", True),
        ("1.1", "1.0.9", True),
        ("1.0.0", "1.0.0", False),
        ("0.9.9", "1.0.0", False),
        ("v2.0.0-beta", "1.9.0", True),
        ("non-valida", "1.0.0", False),
    ],
)
def test_confronto_versioni(remote: str, local: str, expected: bool) -> None:
    assert gu.is_newer(remote, local) is expected


def test_versione_locale_letta_da_file() -> None:
    expected = (Path(__file__).resolve().parents[1] / "version.txt").read_text().strip()
    assert get_version() == expected


def test_parse_release_e_selezione_asset() -> None:
    release = gu.parse_release(RELEASE_PAYLOAD)
    assert release.version == "1.2.0"
    assert gu.select_asset(release, "win32").name.endswith(".exe")
    assert gu.select_asset(release, "darwin").name.endswith("macos.zip")
    assert gu.select_asset(release, "linux").name.endswith("linux.tar.gz")


def test_parse_release_non_valida() -> None:
    with pytest.raises(gu.UpdateError):
        gu.parse_release({"assets": []})


class _FakeResponse(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_fetch_latest_release(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gu.urllib.request, "urlopen", lambda *_a, **_k: _FakeResponse(json.dumps(RELEASE_PAYLOAD).encode())
    )
    assert gu.fetch_latest_release().tag == "v1.2.0"


def test_fetch_errore_di_rete(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise gu.urllib.error.URLError("offline")

    monkeypatch.setattr(gu.urllib.request, "urlopen", boom)
    with pytest.raises(gu.UpdateError):
        gu.fetch_latest_release()


def test_download_asset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data = b"x" * 200_000
    monkeypatch.setattr(gu.urllib.request, "urlopen", lambda *_a, **_k: _FakeResponse(data))
    progress: list[int] = []
    asset = gu.ReleaseAsset("Setup.exe", "https://x/setup.exe", len(data))
    path = gu.download_asset(asset, tmp_path, progress=lambda done, _total: progress.append(done))
    assert path.read_bytes() == data
    assert progress[-1] == len(data)


def test_download_annullato_rimuove_file_parziale(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gu.urllib.request, "urlopen", lambda *_a, **_k: _FakeResponse(b"x" * 1000))
    asset = gu.ReleaseAsset("Setup.exe", "https://x/setup.exe", 1000)
    with pytest.raises(gu.UpdateError):
        gu.download_asset(asset, tmp_path, is_cancelled=lambda: True)
    assert list(tmp_path.iterdir()) == []
