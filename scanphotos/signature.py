"""Vérification des mises à jour signées.

Chaque version publiée porte un fichier signature.txt :
    ligne 1 : albums-marie-france|v<N>|<sha256 du .exe>|<taille en octets>
    ligne 2 : signature Ed25519 de la ligne 1 (base64)
La clé privée ne quitte jamais le Mac de Martin (scripts/signer_version.py) ; le
logiciel n'installe qu'un .exe dont la version, l'empreinte et la taille sont
couvertes par une signature valide de cette clé.
"""
import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

CLE_PUBLIQUE = "FGvin7K6f90Sshsmw6HDd6tHMqEDIqFW5P7o7/rv/g8="
PREFIXE = "albums-marie-france"

# Vecteur signé par la vraie clé : l'autotest prouve que la vérification marche
AUTOTEST = (f"{PREFIXE}|autotest|0|0", "CPh6gYpfwO2W85wMo9s4bcUsSIlAWTLy9tiyYqK5RXO9wYOfBsgNAmWQwA5N/2M63z/IEvA684Z82cOEGWTwBw==")


class SignatureInvalide(Exception):
    pass


def verifier(texte):
    """Contenu de signature.txt -> (version, sha256, taille) si la signature est valide."""
    lignes = texte.strip().splitlines()
    if len(lignes) != 2:
        raise SignatureInvalide("format inattendu")
    manifeste, sig = lignes[0].strip(), lignes[1].strip()
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(CLE_PUBLIQUE)).verify(
            base64.b64decode(sig, validate=True), manifeste.encode())
    except (InvalidSignature, ValueError) as e:
        raise SignatureInvalide("signature refusée") from e
    champs = manifeste.split("|")
    if len(champs) != 4 or champs[0] != PREFIXE:
        raise SignatureInvalide("manifeste inattendu")
    if champs[1] == "autotest":
        return 0, "", 0
    if not (champs[1].startswith("v") and champs[1][1:].isdigit()):
        raise SignatureInvalide("version illisible")
    return int(champs[1][1:]), champs[2].lower(), int(champs[3])


def autotest():
    assert verifier("\n".join(AUTOTEST)) == (0, "", 0)
    faux = AUTOTEST[0].replace("|0|0", "|0|1") + "\n" + AUTOTEST[1]
    try:
        verifier(faux)
    except SignatureInvalide:
        return
    raise AssertionError("une signature falsifiée a été acceptée")
