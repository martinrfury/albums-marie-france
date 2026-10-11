"""Mise à jour automatique depuis les versions publiées sur GitHub.

Au lancement, le .exe compare son numéro de version au dernier publié. Une
version n'est retenue que si son fichier signature.txt est signé par la clé de
Martin (voir signature.py) et couvre ce numéro de version ; le .exe téléchargé
doit ensuite avoir exactement l'empreinte SHA-256 et la taille signées. Un petit
script remplace alors le .exe une fois le logiciel fermé et le relance. Tout
échec (pas d'Internet, signature absente ou fausse, fichier différent) laisse
simplement l'ancienne version démarrer.
"""
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import urllib.request

from scanphotos import signature
from scanphotos.version import VERSION

DEPOT = "martinrfury/albums-marie-france"
API = f"https://api.github.com/repos/{DEPOT}/releases/latest"
TELECHARGEMENTS = f"https://github.com/{DEPOT}/releases/download/"
log = logging.getLogger("albums")


def installed():
    """Vrai seulement pour le .exe fabriqué (pas en développement)."""
    return getattr(sys, "frozen", False) and VERSION > 0


def _get(url, timeout=10):
    if not url.startswith(("https://api.github.com/", TELECHARGEMENTS)):
        raise signature.SignatureInvalide(f"adresse inattendue : {url}")
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "albums-marie-france"})
    return urllib.request.urlopen(req, timeout=timeout)


def latest():
    """(version, url_du_exe, taille, sha256) de la dernière version publiée ET
    correctement signée, ou None."""
    with _get(API, 6) as r:
        rel = json.load(r)
    tag = rel.get("tag_name", "")
    assets = {a["name"]: a for a in rel.get("assets", [])}
    exe = [a for n, a in assets.items() if n.lower().endswith(".exe")]
    if not tag.startswith("v") or not tag[1:].isdigit() or len(exe) != 1 \
            or "signature.txt" not in assets:
        log.info("Version %s ignorée : pas de .exe signé", tag or "?")
        return None
    with _get(assets["signature.txt"]["browser_download_url"]) as r:
        version, sha, size = signature.verifier(r.read(4096).decode("ascii", "replace"))
    if version != int(tag[1:]) or size != exe[0]["size"]:
        raise signature.SignatureInvalide(f"la signature ne couvre pas {tag}")
    return version, exe[0]["browser_download_url"], size, sha


def check():
    """Version plus récente, signée, disponible -> (version, url, taille, sha256)."""
    if not installed():
        return None
    try:
        info = latest()
    except signature.SignatureInvalide as e:
        log.warning("Mise à jour REFUSÉE : %s", e)
        return None
    except Exception as e:  # noqa: BLE001 — pas d'Internet : on démarre normalement
        log.info("Vérification de mise à jour impossible : %s", e)
        return None
    if info and info[0] > VERSION:
        log.info("Mise à jour signée disponible : v%s (installée v%s)", info[0], VERSION)
        return info
    return None


def download(url, size, sha, progress=None):
    """Télécharge le nouveau .exe à côté de l'actuel et vérifie qu'il est bien
    celui qui a été signé ; renvoie son chemin."""
    dest = sys.executable + ".nouveau"
    h = hashlib.sha256()
    done = 0
    with _get(url, 30) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 16):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done / size if size else 0)
    if done != size or h.hexdigest() != sha:
        os.remove(dest)
        raise signature.SignatureInvalide(
            f"le fichier reçu ne correspond pas à la signature ({done}/{size} octets)")
    return dest


def clean_env():
    """Environnement pour relancer le .exe : sans les variables internes de
    PyInstaller héritées de l'instance actuelle (sinon le nouveau .exe cherche
    son dossier _MEIxxxx, effacé à la fermeture -> « Failed to load Python DLL »)."""
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("_PYI") or k.startswith("_MEI"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def install_and_restart(new_exe, args=""):
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
start "" "{exe}" {args}
del "%~f0"
""")
    subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000,  # sans fenêtre
                     env=clean_env())
    log.info("Mise à jour installée, redémarrage")
