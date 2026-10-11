#!/usr/bin/env python3
"""Signe et publie la dernière version en brouillon (à lancer sur le Mac de Martin).

La fabrication GitHub publie chaque .exe en BROUILLON : invisible pour le logiciel
de Marie-France. Ce script ne le signe que si :
  - le brouillon a été fabriqué à partir du commit actuel de ce dossier, identique
    à celui en ligne (main) ;
  - la fabrication de ce commit a réussi (autotests Windows compris) ;
  - le .exe a été déposé par la fabrication GitHub (github-actions[bot]) ;
puis il écrit signature.txt (version + SHA-256 + taille, signés Ed25519 avec la
clé privée qui ne quitte pas ce Mac) et publie la version.

    .venv/bin/python scripts/signer_version.py          # demande confirmation
    .venv/bin/python scripts/signer_version.py --oui    # sans confirmation
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile

from cryptography.hazmat.primitives import serialization

DEPOT = "martinrfury/albums-marie-france"
CLE = os.path.expanduser("~/.config/albums-marie-france/cle_signature_privee.pem")
PREFIXE = "albums-marie-france"


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def stop(msg):
    sys.exit(f"REFUS : {msg}")


def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    releases = json.loads(run("gh", "api", f"repos/{DEPOT}/releases?per_page=20"))
    drafts = [r for r in releases if r["draft"]]
    if not drafts:
        stop("aucune version en brouillon à signer")
    rel = max(drafts, key=lambda r: int(r["tag_name"].lstrip("v") or 0))
    tag, version = rel["tag_name"], int(rel["tag_name"].lstrip("v"))

    run("git", "fetch", "-q", "origin", "main")
    head, remote = run("git", "rev-parse", "HEAD"), run("git", "rev-parse", "origin/main")
    if run("git", "status", "--porcelain", "--untracked-files=no"):
        stop("le dossier contient des modifications non enregistrées")
    if head != remote:
        stop(f"le commit local ({head[:7]}) n'est pas celui en ligne ({remote[:7]})")
    if rel["target_commitish"] != head:
        stop(f"{tag} a été fabriqué depuis {rel['target_commitish'][:7]}, pas depuis {head[:7]}")

    runs = json.loads(run("gh", "run", "list", "-R", DEPOT, "--commit", head,
                          "--json", "conclusion,status,event"))
    if not any(r["status"] == "completed" and r["conclusion"] == "success" for r in runs):
        stop(f"aucune fabrication réussie pour le commit {head[:7]}")

    exes = [a for a in rel["assets"] if a["name"].lower().endswith(".exe")]
    if len(exes) != 1 or any(a["name"] == "signature.txt" for a in rel["assets"]):
        stop(f"{tag} doit contenir exactement un .exe et pas encore de signature")
    exe = exes[0]
    if exe["uploader"]["login"] != "github-actions[bot]":
        stop(f"le .exe a été déposé par {exe['uploader']['login']}, pas par la fabrication")

    with tempfile.TemporaryDirectory() as tmp:
        run("gh", "release", "download", tag, "-R", DEPOT, "-p", exe["name"], "-D", tmp)
        data = open(os.path.join(tmp, exe["name"]), "rb").read()
        if len(data) != exe["size"] or data[:2] != b"MZ":
            stop("le .exe téléchargé ne correspond pas à celui annoncé")
        sha = hashlib.sha256(data).hexdigest()
        manifeste = f"{PREFIXE}|v{version}|{sha}|{len(data)}"
        print(f"Version   : {tag}  (commit {head[:7]} : {run('git', 'log', '-1', '--format=%s')})")
        print(f".exe      : {exe['name']}  {len(data):,} octets")
        print(f"SHA-256   : {sha}")
        if "--oui" not in sys.argv and input("Signer et publier ? (oui/non) ").strip() != "oui":
            stop("annulé")
        cle = serialization.load_pem_private_key(open(CLE, "rb").read(), None)
        sig = base64.b64encode(cle.sign(manifeste.encode())).decode()
        path = os.path.join(tmp, "signature.txt")
        with open(path, "w", encoding="ascii") as f:
            f.write(manifeste + "\n" + sig + "\n")
        run("gh", "release", "upload", tag, path, "-R", DEPOT)
    run("gh", "release", "edit", tag, "-R", DEPOT, "--draft=false", "--latest")
    print(f"{tag} signée et publiée : le logiciel de Marie-France l'installera au prochain lancement.")


if __name__ == "__main__":
    main()
