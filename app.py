"""Scan photos — numérise des tirages par planches de 4, les détoure, les remet
dans le bon sens et les range dans un dossier par album. Tout se fait sur le PC."""
import logging
import logging.handlers
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import cv2
from PIL import Image, ImageTk

from scanphotos import album as alb
from scanphotos import detect, orient, scanner
from scanphotos import maj, ui
from scanphotos.version import VERSION
from scanphotos.ui import BG, CARD, GREEN, RED, TEXT, TEXT2, TEXT3, LINE, px

CONSEIL = ("Conseil : écartez un peu plus les photos et, si elles sont claires, "
           "glissez une feuille de couleur derrière.")
COL = 560  # largeur de la colonne centrale (avant mise à l'échelle)
PRENOM = "Marie-France"
APP_TITLE = f"Les albums de {PRENOM}"


log = logging.getLogger("albums")


def setup_journal():
    """Journal des événements et erreurs : %APPDATA%\\ScanPhotos\\journal.txt."""
    path = os.path.join(os.path.dirname(alb.config_path()), "journal.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    h = logging.handlers.RotatingFileHandler(path, maxBytes=512_000, backupCount=2,
                                             encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    return path


def salutation():
    import datetime
    return "Bonsoir" if datetime.datetime.now().hour >= 18 else "Bonjour"


def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.run(["open", path])


def plural(n, word):
    return f"{n} {word}{'s' if n > 1 else ''}"


class App(tk.Tk):
    def __init__(self):
        ui.dpi_awareness()
        super().__init__()
        fam = ui.init_scale(self)
        self.F = {
            "large": (fam, 28, "bold"), "title": (fam, 20, "bold"),
            "body": (fam, 14), "bodyb": (fam, 14, "bold"), "small": (fam, 12),
            "btn": (fam, 15, "bold"), "field": (fam, 17),
        }
        self.col = px(COL)
        self.title(APP_TITLE)
        self.geometry(f"{px(760)}x{px(700)}")
        self.minsize(px(640), px(620))
        self.configure(bg=BG)
        self.cfg = alb.load_config()
        self.scanner_url = None
        self.scanner_done = False
        self.album = None
        self.jobs = queue.Queue()
        self.page = None
        threading.Thread(target=self._find_scanner, daemon=True).start()
        self.after(200, self._poll)
        self.screen_start() if self.cfg.get("root") else self.screen_root()
        log.info("Démarrage, version %s", VERSION or "développement")
        self.run_bg(maj.check, self._update_found)

    def report_callback_exception(self, exc, val, tb):
        """Erreur imprévue dans l'interface : journalisée, message simple à l'écran."""
        log.error("Erreur dans l'interface", exc_info=(exc, val, tb))
        messagebox.showerror(APP_TITLE, "Un problème est survenu. Fermez le logiciel et "
                                        "rouvrez-le. Si ça recommence, prévenez Martin.")

    # ---------- mise à jour ----------
    def _update_found(self, info):
        if info and not isinstance(info, Exception) and self.album is None:
            self.screen_update(info)

    def screen_update(self, info):
        version, url, size = info
        col = self.new_page()
        self.text(col, "Mise à jour", "large", pady=(0, px(4)))
        self.text(col, "Une nouvelle version du logiciel s'installe. Il va redémarrer tout "
                       "seul dans un instant.", "body", TEXT2, pady=(0, px(24)))
        bar = ui.Activity(col, self.col)
        bar.pack(pady=(0, px(10)))
        bar.start()
        self.pct = self.text(col, "0 %", "small", TEXT3)
        self.pct.config(anchor="center")

        def progress(p):
            self.jobs.put((lambda v: self.pct.winfo_exists() and
                           self.pct.config(text=f"{int(v * 100)} %"), p))

        def done(res):
            if isinstance(res, Exception):
                log.warning("Mise à jour abandonnée : %s", res)
                self.screen_start() if self.cfg.get("root") else self.screen_root()
                return
            maj.install_and_restart(res)
            self.destroy()

        self.run_bg(lambda: maj.download(url, size, progress), done)

    # ---------- mise en page ----------
    def new_page(self):
        if self.page:
            self.page.destroy()
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)
        self.page = outer
        col = tk.Frame(outer, bg=BG, width=self.col)
        col.place(relx=0.5, y=px(48), anchor="n")
        return col

    def text(self, parent, s, font="body", fg=TEXT, bg=BG, pady=(0, 0), **kw):
        l = tk.Label(parent, text=s, font=self.F[font], fg=fg, bg=bg, anchor="w",
                     justify="left", wraplength=self.col - px(40), **kw)
        l.pack(fill="x", pady=pady)
        return l

    def pill(self, parent, s, cmd, kind="primary", full=False, bg=BG):
        return ui.Pill(parent, s, cmd, self.F["btn" if kind == "primary" else "body"],
                       kind=kind, width=self.col if full else None, bg=bg)

    def caption(self, col):
        n = self.album.count()
        self.text(col, f"{self.album.name}  ·  {plural(n, 'photo')}", "small", TEXT3,
                  pady=(0, px(6)))

    # ---------- tâches de fond ----------
    def run_bg(self, fn, done):
        def work():
            try:
                self.jobs.put((done, fn()))
            except Exception as e:  # noqa: BLE001 — affiché à l'utilisatrice
                log.error("Erreur pendant %s", getattr(fn, "__name__", "une tâche"),
                          exc_info=True)
                self.jobs.put((done, e))
        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        try:
            while True:
                done, res = self.jobs.get_nowait()
                done(res)
        except queue.Empty:
            pass
        self.after(150, self._poll)

    # ---------- scanner ----------
    def _find_scanner(self):
        url = self.cfg.get("scanner")
        if not (url and scanner.is_alive(url)):
            found = scanner.discover()
            url = found[0][1] if found else None
            if url:
                self.cfg["scanner"], self.cfg["scanner_name"] = url, found[0][0]
                log.info("Scanner trouvé : %s (%s)", found[0][0], url)
                alb.save_config(self.cfg)
        self.jobs.put((self._scanner_found, url))

    def _scanner_found(self, url):
        self.scanner_url, self.scanner_done = url, True
        if getattr(self, "scan_row", None) and self.scan_row.winfo_exists():
            self._paint_scanner_row()

    def _paint_scanner_row(self):
        for w in self.scan_row.winfo_children():
            w.destroy()
        if not self.scanner_done:
            color, msg = TEXT3, "Recherche du scanner…"
        elif self.scanner_url:
            name = self.cfg.get("scanner_name", "").split(" [")[0]
            color, msg = GREEN, f"Scanner prêt  ·  {name}"
        else:
            color, msg = RED, "Scanner introuvable : vérifiez qu'il est allumé."
        tk.Label(self.scan_row, text="●", font=self.F["small"], fg=color, bg=CARD
                 ).pack(side="left")
        tk.Label(self.scan_row, text=msg, font=self.F["body"], fg=TEXT, bg=CARD,
                 anchor="w").pack(side="left", padx=(px(8), 0), fill="x", expand=True)
        if self.scanner_done and not self.scanner_url:
            ui.Pill(self.scan_row, "Rechercher", self.rescan_network, self.F["body"],
                    kind="link", bg=CARD).pack(side="right")

    def rescan_network(self):
        self.cfg.pop("scanner", None)
        self.scanner_url, self.scanner_done = None, False
        self._paint_scanner_row()
        threading.Thread(target=self._find_scanner, daemon=True).start()

    # ---------- écran 1 : nouvel album ----------
    def screen_start(self):
        col = self.new_page()
        self.text(col, f"{salutation()} {PRENOM}", "body", TEXT3, pady=(0, px(2)))
        self.text(col, "Nouvel album", "large", pady=(0, px(4)))
        self.text(col, "Donnez un nom à l'album, par exemple « Noël 2024 ».", "body",
                  TEXT2, pady=(0, px(20)))
        self.name_var = tk.StringVar()
        field = ui.Field(col, self.col, self.F["field"], self.name_var)
        field.pack(pady=(0, px(14)))
        field.entry.focus_set()
        field.entry.bind("<Return>", lambda _: self.start_album())
        self.pill(col, "Commencer", self.start_album, full=True).pack(pady=(0, px(28)))

        card = ui.Card(col, self.col)
        card.pack()
        self.scan_row = tk.Frame(card.inner, bg=CARD)
        self.scan_row.pack(fill="x")
        self._paint_scanner_row()
        tk.Frame(card.inner, bg=LINE, height=1).pack(fill="x", pady=px(14))
        row = tk.Frame(card.inner, bg=CARD)
        row.pack(fill="x")
        root = self.cfg.get("root")
        info = tk.Frame(row, bg=CARD)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text="Rangement des albums", font=self.F["small"], fg=TEXT3, bg=CARD,
                 anchor="w").pack(fill="x")
        tk.Label(info, text=root or "Pas encore choisi", font=self.F["body"],
                 fg=TEXT if root else RED, bg=CARD, anchor="w", justify="left",
                 wraplength=self.col - px(160)).pack(fill="x")
        ui.Pill(row, "Modifier", self.screen_root, self.F["body"], kind="link",
                bg=CARD).pack(side="right")

        recent = alb.existing_albums(root) if root else []
        if recent:
            self.text(col, "Reprendre un album", "small", TEXT3, pady=(px(24), px(8)))
            chips = tk.Frame(col, bg=BG)
            chips.pack(fill="x")
            for name in recent[:4]:
                ui.Pill(chips, name, lambda n=name: self.name_var.set(n), self.F["small"],
                        kind="secondary").pack(side="left", padx=(0, px(8)))

        v = self.text(col, f"Version {VERSION}" if VERSION else "Version de développement",
                      "small", TEXT3, pady=(px(32), 0))
        v.config(anchor="center")

    # ---------- écran 0 : dossier de rangement ----------
    def screen_root(self):
        col = self.new_page()
        first = not self.cfg.get("root")
        self.text(col, f"Bienvenue {PRENOM}" if first else "Rangement des albums", "large",
                  pady=(0, px(4)))
        self.text(col, "Choisissez le dossier où ranger vos albums photo. Chaque album y "
                       "aura son propre dossier.", "body", TEXT2, pady=(0, px(20)))
        card = ui.Card(col, self.col)
        card.pack(pady=(0, px(20)))
        root = self.cfg.get("root")
        tk.Label(card.inner, text="Dossier actuel" if root else "Exemple", font=self.F["small"],
                 fg=TEXT3, bg=CARD, anchor="w").pack(fill="x")
        example = os.path.join(root or self.pictures_dir(), "Noël 2024", "Noël 2024 001.jpg")
        tk.Label(card.inner, text=example, font=self.F["body"], fg=TEXT, bg=CARD, anchor="w",
                 justify="left", wraplength=self.col - px(40)).pack(fill="x", pady=(px(2), 0))
        self.pill(col, "Choisir un dossier…", self.choose_root, full=True).pack(pady=(0, px(12)))
        if root:
            self.pill(col, "Garder ce dossier", self.screen_start, kind="secondary",
                      full=True).pack()

    @staticmethod
    def pictures_dir():
        """Dossier Images de l'utilisatrice (suit une redirection OneDrive sous Windows)."""
        if sys.platform == "win32":
            try:
                import ctypes
                buf = ctypes.c_wchar_p()
                # FOLDERID_Pictures {33E28130-4E1E-4676-835A-98395C3BC3BB}, octets little-endian
                guid = (ctypes.c_ubyte * 16)(*bytes.fromhex("3081e2331e4e7646835a98395c3bc3bb"))
                if ctypes.windll.shell32.SHGetKnownFolderPath(guid, 0, None,
                                                              ctypes.byref(buf)) == 0:
                    return buf.value
            except Exception:
                pass
        return os.path.join(os.path.expanduser("~"), "Pictures")

    def choose_root(self):
        d = filedialog.askdirectory(title="Où ranger les albums photo ?",
                                    initialdir=self.cfg.get("root") or self.pictures_dir())
        if d:
            self.cfg["root"] = os.path.normpath(d)
            alb.save_config(self.cfg)
            self.screen_start()

    def start_album(self):
        name = alb.clean_name(self.name_var.get())
        if not name:
            messagebox.showinfo(APP_TITLE, "Tapez d'abord le nom de l'album.")
            return
        if not self.cfg.get("root"):
            self.screen_root()
            return
        self.album = alb.Album(self.cfg["root"], name)
        self.screen_prepare()

    # ---------- écran 2 : préparer la planche ----------
    def screen_prepare(self, error=None, tip=None):
        col = self.new_page()
        self.caption(col)
        self.text(col, "Posez vos photos", "large", pady=(0, px(20)))
        card = ui.Card(col, self.col)
        card.pack(pady=(0, px(20)))
        steps = ["Jusqu'à 4 photos sur la vitre",
                 "1 cm d'écart entre elles",
                 "Le haut des photos vers le fond du scanner",
                 "Fermez le capot"]
        for i, s in enumerate(steps, 1):
            r = tk.Frame(card.inner, bg=CARD)
            r.pack(fill="x", pady=px(5))
            ui.badge(r, str(i), px(28), ui.BLUE, font=self.F["small"]).pack(side="left")
            tk.Label(r, text=s, font=self.F["body"], fg=TEXT, bg=CARD, anchor="w"
                     ).pack(side="left", padx=(px(12), 0))
        if error:
            self.text(col, error, "body", RED, pady=(0, px(6) if tip else px(14)))
        if tip:
            self.text(col, tip, "body", TEXT2, pady=(0, px(14)))
        self.scan_btn = self.pill(col, "Scanner", self.do_scan, full=True)
        self.scan_btn.pack(pady=(0, px(12)))
        self.activity = ui.Activity(col, self.col)
        self.hint = self.text(col, "Environ 40 secondes", "small", TEXT3)
        self.hint.config(anchor="center", justify="center")
        end = tk.Frame(col, bg=BG)
        end.pack(fill="x", pady=(px(24), 0))
        if self.album.count():
            ui.Pill(end, "Terminer l'album", self.screen_done, self.F["body"],
                    kind="link").pack()

    def do_scan(self):
        if not self.scanner_url:
            self.screen_prepare("Scanner introuvable : vérifiez qu'il est allumé, puis "
                                "réessayez.")
            if self.scanner_done:
                self.rescan_network_silent()
            return
        self.scan_btn.set_enabled(False, "Scan en cours…")
        self.activity.pack(before=self.hint, pady=(0, px(10)))
        self.activity.start()
        self.hint.config(text="Ne soulevez pas le capot.")
        album, url = self.album, self.scanner_url

        def work():
            path = album.save_scan(scanner.scan(url))
            return path, detect.find_quads(alb.read_image(path))

        self.run_bg(work, self.scan_done)

    def rescan_network_silent(self):
        self.cfg.pop("scanner", None)
        self.scanner_done = False
        threading.Thread(target=self._find_scanner, daemon=True).start()

    def scan_done(self, res):
        if isinstance(res, scanner.ScannerError):
            self.screen_prepare(str(res))
        elif isinstance(res, Exception):
            self.screen_prepare(f"Un problème est survenu : {res}")
        else:
            path, quads = res
            log.info("Scan : %s cadre(s) proposé(s) dans « %s »", len(quads), self.album.name)
            self.screen_check(path, quads)

    # ---------- écran 3 : vérifier les cadres de la planche ----------
    def screen_check(self, scan_path, quads):
        """La planche avec un cadre par photo (4 coins déplaçables, loupe) ; elle
        ajuste, ajoute ou supprime des cadres, puis valide la planche entière.
        Deux colonnes pour que les boutons restent visibles sur tout écran."""
        if self.page:
            self.page.destroy()
        page = tk.Frame(self, bg=BG)
        page.pack(fill="both", expand=True)
        self.page = page
        self.check = (scan_path, quads)  # pour « Corriger les cadres » ensuite
        img = alb.read_image(scan_path)
        side = px(300)
        avail_h = self.winfo_screenheight() - px(150)  # barre de titre, barre des tâches
        avail_w = self.winfo_screenwidth() - px(80)
        self.geometry(f"{avail_w}x{avail_h}+{px(20)}+{px(20)}")

        left = tk.Frame(page, bg=BG)
        right = tk.Frame(page, bg=BG, width=side)
        left.pack(side="left", fill="y", padx=(px(32), px(24)), pady=px(24))
        right.pack(side="left", fill="y", pady=px(32))
        count = tk.Label(right, font=self.F["title"], fg=TEXT, bg=BG, anchor="w")
        ok = ui.Pill(right, "Valider la planche", lambda: self.validate_planche(editor),
                     self.F["btn"], width=side, bg=BG)

        def changed():
            n = len(editor.quads)
            count.config(text=plural(n, "photo") if n else "Aucune photo")
            ok.set_enabled(n > 0)

        editor = ui.FrameEditor(left, img, avail_w - side - px(96), avail_h - px(48),
                                quads=quads, on_change=changed)
        editor.pack(anchor="n")

        n = self.album.count()
        tk.Label(right, text=f"{self.album.name}  ·  {plural(n, 'photo')}", font=self.F["small"],
                 fg=TEXT3, bg=BG, anchor="w").pack(fill="x", pady=(0, px(6)))
        tk.Label(right, text="Vérifiez les cadres", font=self.F["large"], fg=TEXT, bg=BG,
                 anchor="w").pack(fill="x", pady=(0, px(10)))
        intro = ("Chaque photo a un cadre. Déplacez un coin pour l'ajuster ; la loupe "
                 "vous aide à viser." if quads else
                 "Aucune photo trouvée automatiquement. Ajoutez un cadre par photo, puis "
                 "placez ses 4 coins.")
        tk.Label(right, text=intro, font=self.F["body"], fg=TEXT2, bg=BG, anchor="w",
                 justify="left", wraplength=side).pack(fill="x", pady=(0, px(16)))
        count.pack(fill="x", pady=(0, px(12)))
        ok.pack(pady=(0, px(10)))
        ui.Pill(right, "+  Ajouter un cadre", editor.add_frame, self.F["body"],
                kind="secondary", width=side).pack(pady=(0, px(10)))
        ui.Pill(right, "Supprimer le cadre sélectionné", editor.delete_selected, self.F["body"],
                kind="secondary", width=side).pack(pady=(0, px(18)))
        tk.Label(right, text="Deux photos dans un même cadre ? Réduisez-le sur la première "
                             "et ajoutez un cadre pour la seconde.", font=self.F["small"],
                 fg=TEXT3, bg=BG, anchor="w", justify="left",
                 wraplength=side).pack(fill="x", pady=(0, px(18)))
        ui.Pill(right, "Refaire le scan", lambda: self.screen_prepare(tip=CONSEIL),
                self.F["body"], kind="link", bg=BG).pack(anchor="w")
        changed()

    def validate_planche(self, editor):
        scan_path, quads = self.check[0], editor.quads_full()
        self.check = (scan_path, quads)
        album = self.album

        def work():
            img = alb.read_image(scan_path)
            return album.add_photos([orient.upright(detect.crop_quad(img, q)) for q in quads])

        def done(res):
            if isinstance(res, Exception):
                messagebox.showerror(APP_TITLE, f"Un problème est survenu : {res}")
                return
            log.info("Planche validée : %s photo(s) dans « %s »", len(res), album.name)
            self.screen_result(res)

        self.run_bg(work, done)

    # ---------- écran 4 : résultat ----------
    def screen_result(self, files):
        col = self.new_page()
        self.caption(col)
        head = tk.Frame(col, bg=BG)
        head.pack(fill="x", pady=(0, px(20)))
        ui.badge(head, "✓", px(34), GREEN, font=self.F["bodyb"], bg=BG).pack(side="left")
        tk.Label(head, text=plural(len(files), "photo") + (" ajoutées" if len(files) > 1
                 else " ajoutée"), font=self.F["large"], fg=TEXT, bg=BG
                 ).pack(side="left", padx=(px(12), 0))
        card = ui.Card(col, self.col, pad=16)
        card.pack(pady=(0, px(22)))
        grid = tk.Frame(card.inner, bg=CARD)
        grid.pack()
        per_row = min(len(files), 4)
        size = (self.col - px(32) - px(12) * (per_row - 1)) // max(per_row, 3)
        for i, p in enumerate(files):
            cell = tk.Frame(grid, bg=CARD)
            cell.grid(row=i // 4, column=i % 4, padx=(0 if i % 4 == 0 else px(12), 0),
                      pady=(0, px(10)), sticky="n")
            box = tk.Frame(cell, bg=CARD, width=size, height=size)
            box.pack()
            box.pack_propagate(False)
            img_lbl = tk.Label(box, bg=CARD, bd=0)
            img_lbl.place(relx=0.5, rely=0.5, anchor="center")
            self._set_thumb(img_lbl, p, size)
            ui.Pill(cell, "↻  Tourner", lambda p=p, l=img_lbl, s=size: self.rotate(p, l, s),
                    self.F["small"], kind="link", bg=CARD).pack(pady=(px(6), 0))
        self.pill(col, "Planche suivante", self.screen_prepare, full=True
                  ).pack(pady=(0, px(12)))
        row = tk.Frame(col, bg=BG)
        row.pack()
        self.pill(row, "Corriger les cadres", self.fix_frames, kind="secondary"
                  ).pack(side="left", padx=px(6))
        self.pill(row, "Terminer l'album", self.screen_done, kind="secondary"
                  ).pack(side="left", padx=px(6))

    def _set_thumb(self, lbl, path, size):
        im = Image.fromarray(cv2.cvtColor(alb.read_image(path), cv2.COLOR_BGR2RGB))
        im.thumbnail((size, size), Image.LANCZOS)
        tkimg = ImageTk.PhotoImage(im)
        lbl.config(image=tkimg)
        lbl.image = tkimg

    def rotate(self, path, lbl, size):
        self.album.rotate(path)
        self._set_thumb(lbl, path, size)

    def fix_frames(self):
        """Retour à la planche : les photos de la planche vont à la corbeille et les
        cadres validés sont reproposés tels quels."""
        self.album.undo_last()
        self.screen_check(*self.check)

    # ---------- écran 5 : fin ----------
    def screen_done(self):
        col = self.new_page()
        n = self.album.count()
        ui.badge(col, "✓", px(64), GREEN, font=self.F["large"], bg=BG).pack(pady=(px(24), px(18)))
        t = self.text(col, f"Bravo {PRENOM}", "large", pady=(0, px(4)))
        t.config(anchor="center")
        s = self.text(col, f"Album terminé : {plural(n, 'photo')} dans « {self.album.name} »", "body", TEXT2,
                      pady=(0, px(4)))
        s.config(anchor="center")
        d = self.text(col, self.album.dir, "small", TEXT3, pady=(0, px(28)))
        d.config(anchor="center", justify="center")
        self.pill(col, "Ouvrir le dossier", lambda: open_folder(self.album.dir), full=True
                  ).pack(pady=(0, px(12)))
        self.pill(col, "Nouvel album", self.screen_start, kind="secondary", full=True).pack()


def selftest():
    """Vérifie que le .exe embarque tout et que chaque écran s'affiche
    (appelé par la fabrication sous Windows : --selftest)."""
    import tempfile
    import numpy as np
    from zeroconf import Zeroconf
    Zeroconf().close()
    planche = np.full((4217, 2550, 3), 245, np.uint8)
    planche[400:1700, 300:2200] = (40, 90, 160)      # une photo paysage
    planche[2100:3900, 600:1800] = (60, 140, 70)     # une photo portrait
    photos = detect.split_photos(planche)
    assert len(photos) == 2, f"détourage : {len(photos)} photo(s) au lieu de 2"
    photos = [orient.upright(p) for p in photos]    # charge le modèle de visages embarqué

    root = tempfile.mkdtemp(prefix="albums_test_")
    app = App()
    app.cfg = {"root": root}                         # ne touche pas la vraie config
    app.screen_root()
    app.screen_start()
    app.name_var.set("Noël 2024 é")                  # chemin accentué
    app.start_album()
    album = app.album
    ok, buf = cv2.imencode(".jpg", planche)
    scan = album.save_scan(buf.tobytes())
    app.run_bg = lambda fn, done: done(fn())         # tâches de fond en direct pour le test

    def editor():
        def walk(w):
            for c in w.winfo_children():
                yield c
                yield from walk(c)
        return next(w for w in walk(app.page) if isinstance(w, ui.FrameEditor))

    app.scan_done((scan, []))                        # rien trouvé : écran vide
    assert len(editor().quads) == 0
    app.scan_done((scan, detect.find_quads(planche)))
    ed = editor()
    assert len(ed.quads) == 2, f"cadres : {len(ed.quads)} au lieu de 2"
    ed.add_frame()                                   # « Ajouter un cadre »
    ed._loupe(10, 10)                                # loupe au bord
    ed.delete_selected()                             # puis le supprimer
    app.validate_planche(ed)
    files = album.last
    assert album.count() == 2, f"album : {album.count()} fichier(s) au lieu de 2"
    app.rotate(files[0], tk.Label(app), 100)
    app.fix_frames()                                 # « Corriger les cadres »
    assert album.count() == 0 and len(os.listdir(os.path.join(album.hidden, "corbeille"))) == 2
    app.validate_planche(editor())
    assert album.count() == 2
    app.screen_done()
    app.run_bg = lambda *a: None
    app.screen_update((VERSION + 1, "https://example.invalid/x.exe", 1))  # écran seul
    app.update()
    app.destroy()


if __name__ == "__main__":
    if "--test-maj" in sys.argv:
        # Fabrication : rejoue une mise à jour complète (copie de soi-même en
        # « nouvelle version », remplacement, relance) ; la relance fait l'autotest.
        import shutil
        nouveau = sys.executable + ".nouveau"
        shutil.copy2(sys.executable, nouveau)
        maj.install_and_restart(nouveau, args="--selftest")
        sys.exit(0)
    if "--selftest" in sys.argv:
        import tempfile
        import traceback
        out = os.path.join(tempfile.gettempdir(), "albums_selftest.txt")
        try:
            selftest()
            report, code = "OK", 0
        except Exception:  # noqa: BLE001 — rapport complet pour la fabrication
            report, code = traceback.format_exc(), 1
        with open(out, "w", encoding="utf-8") as f:
            f.write(report)
        sys.exit(code)
    setup_journal()
    App().mainloop()
