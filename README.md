# Scan photos

Logiciel Windows pour numériser des tirages photo sur un scanner réseau (eSCL / AirScan,
testé sur HP OfficeJet Pro 7720). Elle donne un nom d'album, pose jusqu'à 4 photos
sur la vitre, clique sur « Scanner » : les photos sont détourées, redressées, remises dans
le bon sens (visages) et rangées dans `<dossier principal>\<ALBUM>\<ALBUM> 001.jpg`.

- Tout tourne sur le PC, hors ligne (OpenCV + détecteur de visages YuNet).
- Scans bruts gardés dans `<ALBUM>\.scans\` (caché) ; « Refaire ce scan » déplace la
  planche dans `.scans\corbeille\` (rien n'est supprimé).
- Réglages : `%APPDATA%\ScanPhotos\config.json` (dossier principal, scanner).

## Fabriquer et publier
Chaque push sur `main` lance GitHub Actions (Windows) : fabrication du .exe,
autotest du .exe lui-même (`--selftest` : imports, détourage, modèle de visages,
tous les écrans), puis publication de la version `vN` (N = numéro de fabrication).

## Publier une version (signature)
La fabrication dépose le .exe en **brouillon**, invisible pour le logiciel installé.
Sur le Mac de Martin : `.venv/bin/python scripts/signer_version.py` vérifie que le
brouillon vient du commit en ligne et d'une fabrication réussie, signe
(version + SHA-256 + taille, Ed25519) avec la clé privée
`~/.config/albums-marie-france/cle_signature_privee.pem` (jamais dans le dépôt), puis
publie. Le logiciel refuse toute version dont la signature, la version ou
l'empreinte ne correspondent pas. **Sans cette clé, plus aucune mise à jour possible**
(il faudrait réinstaller à la main une version portant une nouvelle clé publique).

## Mises à jour
Au lancement, le logiciel compare sa version à la dernière publiée ; si elle est
plus récente, il la télécharge, se remplace et redémarre (seulement avant
l'ouverture d'un album). Sans Internet ou en cas d'échec, l'ancienne version démarre.
Journal des événements et erreurs : `%APPDATA%\ScanPhotos\journal.txt`.

## Tester sur Mac
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python app.py
