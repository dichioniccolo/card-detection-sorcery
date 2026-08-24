"""Aggiornamento automatico dell'eseguibile dalle release di GitHub.

L'applicazione gira come singolo .exe scaricato a mano: senza questo modulo,
per avere una correzione bisogna accorgersi che esiste e riscaricare il file.

Come funziona:
- si chiede a GitHub qual e' l'ultima release STABILE (`releases/latest`
  ignora le prerelease, quindi la "latest" mobile costruita a ogni push su
  main non viene mai proposta a chi usa l'applicazione);
- se la versione e' piu' recente di quella in esecuzione, si scarica il file
  .exe allegato alla release in un temporaneo ACCANTO all'eseguibile (stesso
  disco: lo scambio finale deve essere atomico);
- l'eseguibile in esecuzione non si puo' cancellare, ma su Windows si puo'
  rinominare: si sposta da parte con suffisso `.old`, si mette il nuovo al suo
  posto e si riavvia. Il `.old` sparisce al primo avvio successivo.

Solo urllib e hashlib: niente dipendenze in piu' da infilare nell'eseguibile.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from version import APP_VERSION

REPO = "dichioniccolo/depositscan-replica"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"

# Nome dell'allegato da scaricare: la release contiene un solo .exe, ma il
# nome porta la versione, quindi si riconosce dal prefisso e dall'estensione.
ASSET_PREFIX = "CardsDetectionSorcery"
ASSET_SUFFIX = ".exe"

TIMEOUT = 15          # secondi per ogni richiesta di rete
CHUNK = 256 * 1024    # blocco di download, per riportare l'avanzamento

# Suffisso dell'eseguibile spodestato, cancellato al riavvio.
OLD_SUFFIX = ".old"


@dataclass
class Release:
    """Una release piu' recente di quella in esecuzione."""
    version: str
    asset_name: str
    asset_url: str
    size: int
    digest: str    # "sha256:..." se GitHub lo espone, altrimenti ""


def current_version() -> str:
    return APP_VERSION


def is_frozen() -> bool:
    """Vero se giriamo dentro l'eseguibile PyInstaller.

    Dai sorgenti non c'e' niente da sostituire: l'aggiornamento si puo'
    annunciare ma non applicare.
    """
    return bool(getattr(sys, "frozen", False))


def executable_path() -> Path:
    return Path(sys.executable).resolve()


def _parse_version(text: str):
    """Da 'v1.4.2' a (1, 4, 2). None se non e' una versione confrontabile.

    Le build di sviluppo ('sviluppo', 'main-1a2b3c') non hanno numero: per
    loro qualunque release pubblicata e' piu' recente.
    """
    core = text.strip().lstrip("vV").split("-")[0].split("+")[0]
    if not core:
        return None
    parts = core.split(".")
    if not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def is_newer(candidate: str, installed: str) -> bool:
    """Vero se `candidate` e' una versione successiva a `installed`."""
    new, old = _parse_version(candidate), _parse_version(installed)
    if new is None:
        return False
    if old is None:
        # build di sviluppo: qualunque release e' un aggiornamento
        return True
    # (1, 4) e (1, 4, 0) sono la stessa versione
    length = max(len(new), len(old))
    return new + (0,) * (length - len(new)) > old + (0,) * (length - len(old))


def _get_json(url: str, timeout: int = TIMEOUT):
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{ASSET_PREFIX}/{APP_VERSION}",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_for_update(timeout: int = TIMEOUT):
    """Ritorna la Release da installare, o None se siamo gia' aggiornati.

    Solleva OSError/urllib.error.URLError se la rete non risponde: chi chiama
    decide se e' il caso di dirlo all'utente (all'avvio no, se l'utente ha
    chiesto lui il controllo si').
    """
    try:
        data = _get_json(LATEST_RELEASE_URL, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # nessuna release stabile pubblicata: solo le build di sviluppo,
            # che non vanno proposte
            return None
        raise
    version = str(data.get("tag_name") or data.get("name") or "").strip()
    if not version or not is_newer(version, APP_VERSION):
        return None

    for asset in data.get("assets", []):
        name = str(asset.get("name", ""))
        if name.startswith(ASSET_PREFIX) and name.endswith(ASSET_SUFFIX):
            return Release(
                version=version,
                asset_name=name,
                asset_url=asset["browser_download_url"],
                size=int(asset.get("size") or 0),
                digest=str(asset.get("digest") or ""),
            )
    # release senza eseguibile allegato: non c'e' niente da scaricare
    return None


def download(release: Release, progress=None, timeout: int = TIMEOUT) -> Path:
    """Scarica l'eseguibile accanto a quello in uso e ne ritorna il percorso.

    `progress(scaricati, totale)` viene chiamata durante il download; totale e'
    0 se il server non dichiara la dimensione.

    Il file finisce nella cartella dell'eseguibile e non fra i temporanei di
    sistema: `os.replace` e' atomico solo dentro lo stesso disco, e la cartella
    temporanea puo' stare altrove.
    """
    target_dir = executable_path().parent if is_frozen() else Path(tempfile.gettempdir())
    request = urllib.request.Request(release.asset_url, headers={
        "Accept": "application/octet-stream",
        "User-Agent": f"{ASSET_PREFIX}/{APP_VERSION}",
    })

    sha = hashlib.sha256()
    downloaded = 0
    fd, tmp_name = tempfile.mkstemp(prefix=".update-", suffix=ASSET_SUFFIX,
                                    dir=str(target_dir))
    tmp = Path(tmp_name)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, \
                os.fdopen(fd, "wb") as out:
            total = int(response.headers.get("Content-Length") or release.size or 0)
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                out.write(block)
                sha.update(block)
                downloaded += len(block)
                if progress:
                    progress(downloaded, total)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    try:
        _verify(tmp, release, downloaded, sha.hexdigest())
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def _verify(path: Path, release: Release, downloaded: int, digest: str):
    """Controlla che sia arrivato tutto e che sia il file giusto.

    Un download troncato darebbe un eseguibile che non parte, e ce ne
    accorgeremmo solo dopo aver messo da parte quello buono.
    """
    if release.size and downloaded != release.size:
        raise OSError(f"download incompleto: {downloaded} byte invece di {release.size}")
    expected = release.digest.split(":", 1)[-1].strip().lower() if release.digest else ""
    if expected and expected != digest:
        raise OSError("il file scaricato non corrisponde alla release (checksum diverso)")
    if path.stat().st_size == 0:
        raise OSError("il file scaricato e' vuoto")


def apply_update(downloaded: Path, restart: bool = True):
    """Mette il file scaricato al posto dell'eseguibile e riavvia.

    L'eseguibile in esecuzione non si puo' sovrascrivere, ma si puo'
    rinominare: da li' in poi il nome libero e' quello nuovo. Se qualcosa va
    storto a meta', si rimette al suo posto il vecchio: meglio restare alla
    versione precedente che non avere piu' l'applicazione.
    """
    if not is_frozen():
        raise RuntimeError("aggiornamento possibile solo sull'eseguibile, non dai sorgenti")

    target = executable_path()
    backup = target.with_name(target.name + OLD_SUFFIX)
    backup.unlink(missing_ok=True)

    os.replace(target, backup)
    try:
        os.replace(downloaded, target)
        os.chmod(target, backup.stat().st_mode)
    except BaseException:
        os.replace(backup, target)
        raise

    if restart:
        subprocess.Popen([str(target)], close_fds=True)
    return target


def cleanup_previous():
    """Cancella l'eseguibile della versione precedente, se e' rimasto li'.

    Va chiamata all'avvio: e' il primo momento in cui il file non e' piu' in
    uso da nessuno.
    """
    if not is_frozen():
        return
    target = executable_path()
    try:
        target.with_name(target.name + OLD_SUFFIX).unlink(missing_ok=True)
    except OSError:
        # ancora in uso (avvio doppio): ci riprova il prossimo avvio
        pass
