"""Verifica e download degli aggiornamenti da GitHub Releases (senza dipendenze Qt)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import GITHUB_REPO

API_LATEST_RELEASE = "https://api.github.com/repos/{repo}/releases/latest"
USER_AGENT = "FindDocument-Updater"


class UpdateError(Exception):
    """Errore di rete o di formato durante la verifica/download degli aggiornamenti."""


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    size: int


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    notes: str
    html_url: str
    assets: list[ReleaseAsset] = field(default_factory=list)


def parse_version(value: str) -> tuple[int, ...]:
    """Converte 'v1.2.3' o '1.2' in una tupla confrontabile (1, 2, 3)."""
    numbers = re.findall(r"\d+", value.strip().lstrip("vV").split("-")[0])
    if not numbers:
        raise ValueError(f"Versione non valida: {value!r}")
    parts = [int(n) for n in numbers[:4]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    try:
        return parse_version(remote) > parse_version(local)
    except ValueError:
        return False


def parse_release(payload: dict) -> ReleaseInfo:
    try:
        tag = payload["tag_name"]
        assets = [
            ReleaseAsset(a["name"], a["browser_download_url"], int(a.get("size", 0)))
            for a in payload.get("assets", [])
        ]
        return ReleaseInfo(
            version=tag.lstrip("vV"),
            tag=tag,
            notes=payload.get("body") or "",
            html_url=payload.get("html_url") or "",
            assets=assets,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError("Risposta di GitHub non valida") from exc


def fetch_latest_release(repo: str = GITHUB_REPO, timeout: float = 10.0) -> ReleaseInfo:
    request = urllib.request.Request(
        API_LATEST_RELEASE.format(repo=repo),
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("Nessuna release pubblicata") from exc
        raise UpdateError(f"Errore HTTP {exc.code} da GitHub") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise UpdateError(f"Impossibile contattare GitHub: {exc}") from exc
    return parse_release(payload)


def select_asset(release: ReleaseInfo, platform: str = sys.platform) -> ReleaseAsset | None:
    """Sceglie il pacchetto adatto al sistema operativo corrente."""
    if platform.startswith("win"):
        patterns = [r"setup.*\.exe$", r"\.exe$"]
    elif platform == "darwin":
        patterns = [r"macos.*\.(dmg|zip)$", r"\.dmg$"]
    else:
        patterns = [r"linux.*\.(tar\.gz|appimage)$"]
    for pattern in patterns:
        for asset in release.assets:
            if re.search(pattern, asset.name, re.IGNORECASE):
                return asset
    return None


def download_asset(
    asset: ReleaseAsset,
    destination_dir: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
    timeout: float = 30.0,
) -> Path:
    """Scarica l'asset in una cartella temporanea e restituisce il percorso del file."""
    destination_dir = destination_dir or Path(tempfile.mkdtemp(prefix="finddocument_update_"))
    target = destination_dir / Path(asset.name).name
    partial = target.with_name(target.name + ".part")
    request = urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(partial, "wb") as fh:
            total = int(response.headers.get("Content-Length") or asset.size or 0)
            received = 0
            while True:
                if is_cancelled is not None and is_cancelled():
                    raise UpdateError("Download annullato")
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                received += len(chunk)
                if progress is not None:
                    progress(received, total)
        if total and received != total:
            raise UpdateError("Download incompleto")
        os.replace(partial, target)
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"Download fallito: {exc}") from exc
    return target


def launch_installer(path: Path) -> bool:
    """Avvia l'installer scaricato. Restituisce True se l'app deve chiudersi per completarlo."""
    if sys.platform.startswith("win") and path.suffix.lower() == ".exe":
        # DETACHED_PROCESS: l'installer sopravvive alla chiusura dell'applicazione
        subprocess.Popen([str(path)], creationflags=0x00000008, close_fds=True)  # noqa: S603
        return True
    return False
