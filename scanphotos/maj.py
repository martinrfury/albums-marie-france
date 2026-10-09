"""Mise à jour automatique depuis les versions publiées sur GitHub.

Au lancement, le .exe compare son numéro de version au dernier publié. Si une
version plus récente existe, il la télécharge, puis un petit script remplace le
.exe une fois le logiciel fermé et le relance. Tout échec (pas d'Internet,
téléchargement incomplet) laisse simplement l'ancienne version démarrer.
"""
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.request

from scanphotos.version import VERSION

DEPOT = "martinrfury/albums-marie-france"
API = f"https://api.github.com/repos/{DEPOT}/releases/latest"
log = logging.getLogger("albums")


def installed():
    """Vrai seulement pour le .exe fabriqué (pas en développement)."""
    return getattr(sys, "frozen", False) and VERSION > 0


def latest():
    """(version, url_du_exe, taille) de la dernière version publiée, ou None."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "albums-marie-france"})
    with urllib.request.urlopen(req, timeout=6) as r:
        rel = json.load(r)
    tag = rel.get("tag_name", "")
    exe = [a for a in rel.get("assets", []) if a["name"].lower().endswith(".exe")]
    if not tag.startswith("v") or not tag[1:].isdigit() or not exe:
        return None
    return int(tag[1:]), exe[0]["browser_download_url"], exe[0]["size"]


def check():
    """Version plus récente disponible -> (version, url, taille), sinon None."""
    if not installed():
        return None
    try:
        info = latest()
    except Exception as e:  # noqa: BLE001 — pas d'Internet : on démarre normalement
        log.info("Vérification de mise à jour impossible : %s", e)
        return None
    if info and info[0] > VERSION:
        log.info("Mise à jour disponible : v%s (installée v%s)", info[0], VERSION)
        return info
    return None


def download(url, size, progress=None):
    """Télécharge le nouveau .exe à côté de l'actuel ; renvoie son chemin."""
    dest = sys.executable + ".nouveau"
    req = urllib.request.Request(url, headers={"User-Agent": "albums-marie-france"})
    done = 0
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 16):
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done / size if size else 0)
    with open(dest, "rb") as f:
        head = f.read(2)
    if done != size or head != b"MZ":  # incomplet ou pas un programme Windows
        os.remove(dest)
        raise OSError(f"fichier reçu invalide ({done}/{size} octets)")
    return dest


def install_and_restart(new_exe):
    """Remplace le .exe après la fermeture du logiciel, puis le relance."""
    exe = sys.executable
    bat = os.path.join(tempfile.gettempdir(), "albums_maj.bat")
    with open(bat, "w", encoding="mbcs") as f:
        f.write(f"""@echo off
rem Attend la fermeture du logiciel, remplace le .exe, le relance.
set /a n=0
:attente
ping -n 2 127.0.0.1 >nul
move /y "{new_exe}" "{exe}" >nul 2>&1
if errorlevel 1 (
  set /a n+=1
  if %n% lss 30 goto attente
)
start "" "{exe}"
del "%~f0"
""")
    subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)  # sans fenêtre
    log.info("Mise à jour installée, redémarrage")
