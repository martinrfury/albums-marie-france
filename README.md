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

## Mises à jour
Au lancement, le logiciel compare sa version à la dernière publiée ; si elle est
plus récente, il la télécharge, se remplace et redémarre (seulement avant
l'ouverture d'un album). Sans Internet ou en cas d'échec, l'ancienne version démarre.
Journal des événements et erreurs : `%APPDATA%\ScanPhotos\journal.txt`.

## Tester sur Mac
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python app.py
