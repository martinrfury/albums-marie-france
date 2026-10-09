"""Rangement : un dossier par album, fichiers « <ALBUM> 001.jpg », scans bruts cachés.

Toutes les lectures/écritures d'image passent par imencode/imdecode : cv2.imwrite
échoue en silence sur les chemins accentués sous Windows (« Noël », « Hélène »).
"""
import json
import os
import re
import shutil
import sys

import cv2
import numpy as np

HIDDEN = ".scans"  # scans bruts de chaque planche + corbeille


def config_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "ScanPhotos", "config.json")


def load_config():
    try:
        with open(config_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    os.makedirs(os.path.dirname(config_path()), exist_ok=True)
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def clean_name(name):
    """Nom d'album utilisable comme dossier Windows."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    return re.sub(r"\s+", " ", name).strip(" .")[:80]


def read_image(path):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def write_image(path, img):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise OSError(f"encodage impossible : {path}")
    buf.tofile(path)


def _hide(path):
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(path, 0x2)  # FILE_ATTRIBUTE_HIDDEN


class Album:
    def __init__(self, root, name):
        self.name = clean_name(name)
        self.dir = os.path.join(root, self.name)
        self.hidden = os.path.join(self.dir, HIDDEN)
        os.makedirs(self.hidden, exist_ok=True)
        _hide(self.hidden)
        self.last = []  # fichiers de la dernière planche
        self.last_scan = None  # scan brut de la dernière planche

    def _numbers(self, folder, prefix):
        pat = re.compile(re.escape(prefix) + r" (\d{3,})(?: - planche)?\.jpg$", re.I)
        return [int(m.group(1)) for f in os.listdir(folder) if (m := pat.match(f))]

    def count(self):
        return len(self._numbers(self.dir, self.name))

    def save_scan(self, jpeg_bytes):
        n = max(self._numbers(self.hidden, "planche"), default=0) + 1
        path = os.path.join(self.hidden, f"planche {n:03d}.jpg")
        with open(path, "wb") as f:
            f.write(jpeg_bytes)
        self.last_scan = path
        return path

    def add_photos(self, imgs):
        n = max(self._numbers(self.dir, self.name), default=0)
        self.last = []
        for img in imgs:
            n += 1
            p = os.path.join(self.dir, f"{self.name} {n:03d}.jpg")
            write_image(p, img)
            self.last.append(p)
        return self.last

    def keep_whole_scan(self):
        """Détourage raté : range la planche entière comme une seule image (à
        redécouper plus tard) et met les découpes ratées à la corbeille."""
        self.undo_last()
        n = max(self._numbers(self.dir, self.name), default=0) + 1
        p = os.path.join(self.dir, f"{self.name} {n:03d} - planche.jpg")
        shutil.copy2(self.last_scan, p)
        self.last = [p]
        return p

    def rotate(self, path):
        img = read_image(path)
        write_image(path, cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE))

    def undo_last(self):
        """« Refaire ce scan » : met la dernière planche à la corbeille (rien n'est supprimé)."""
        trash = os.path.join(self.hidden, "corbeille")
        os.makedirs(trash, exist_ok=True)
        for p in self.last:
            if os.path.exists(p):
                dst = os.path.join(trash, os.path.basename(p))
                i = 1
                while os.path.exists(dst):
                    base, ext = os.path.splitext(os.path.basename(p))
                    dst = os.path.join(trash, f"{base} ({i}){ext}")
                    i += 1
                shutil.move(p, dst)
        self.last = []


def existing_albums(root):
    try:
        return sorted((d for d in os.listdir(root)
                       if os.path.isdir(os.path.join(root, d, HIDDEN))),
                      key=lambda d: -os.path.getmtime(os.path.join(root, d)))
    except OSError:
        return []
