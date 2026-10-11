"""Widgets façon Apple pour Tkinter : boutons pilule, cartes et champ arrondis.

Les formes arrondies sont dessinées avec Pillow en sur-échantillonnage (bords
lissés), car le Canvas Tk n'anticrénèle pas sous Windows.
"""
import sys
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageTk

# Palette FURYLIVE (codes Apple)
BG = "#f5f5f7"
CARD = "#ffffff"
TEXT = "#1d1d1f"
TEXT2 = "#6e6e73"
TEXT3 = "#8e8e93"
LINE = "#e8e8ed"
FIELD_LINE = "#d1d1d6"
BLUE = "#0071e3"
BLUE_HOVER = "#0077ed"
BLUE_PRESS = "#006edb"
GREEN = "#34c759"
RED = "#ff3b30"
GREY_BTN = "#e8e8ed"
GREY_HOVER = "#dcdce1"

SS = 4  # sur-échantillonnage des formes
S = 1.0  # facteur d'échelle écran (125 %, 150 %… sous Windows)


def init_scale(root):
    """À appeler une fois la fenêtre créée : règle l'échelle et les polices."""
    global S
    if sys.platform == "win32":
        S = max(1.0, root.winfo_fpixels("1i") / 96)
    fams = set(tkfont.families(root))
    for name in ("Segoe UI Variable Display", "Segoe UI", "SF Pro Display",
                 "SF Pro Text", "Helvetica Neue", "Helvetica", "Arial"):
        if name in fams:
            return name
    return "TkDefaultFont"


def px(n):
    return int(round(n * S))


def dpi_awareness():
    """Évite le flou de Windows sur les écrans agrandis (avant de créer Tk)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def rounded_image(w, h, r, fill, outline=None, width=1, bg=BG):
    """PhotoImage d'un rectangle arrondi lissé, posé sur la couleur bg."""
    W, H = w * SS, h * SS
    im = Image.new("RGB", (W, H), _hex(bg))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=r * SS, fill=_hex(fill),
                        outline=_hex(outline) if outline else None,
                        width=width * SS if outline else 0)
    return ImageTk.PhotoImage(im.resize((w, h), Image.LANCZOS))


class Pill(tk.Label):
    """Bouton pilule. kind = primary (bleu) | secondary (gris) | link (texte bleu)."""

    def __init__(self, parent, text, command, font, kind="primary", width=None,
                 height=None, bg=BG):
        self.kind, self.command, self.enabled = kind, command, True
        self.font_obj = tkfont.Font(font=font)
        self.font_ul = self.font_obj.copy()
        self.font_ul.configure(underline=True)
        self.bg_parent = bg
        self.w = width or self.font_obj.measure(text) + px(44)
        self.h = height or px(50 if kind == "primary" else 40)
        super().__init__(parent, text=text, font=font, bd=0, highlightthickness=0,
                         compound="center", cursor="hand2", bg=bg)
        self._paint("normal")
        self.bind("<Enter>", lambda _: self.enabled and self._paint("hover"))
        self.bind("<Leave>", lambda _: self.enabled and self._paint("normal"))
        self.bind("<ButtonPress-1>", lambda _: self.enabled and self._paint("press"))
        self.bind("<ButtonRelease-1>", self._click)

    def _colors(self, state):
        if self.kind == "primary":
            fill = {"normal": BLUE, "hover": BLUE_HOVER, "press": BLUE_PRESS,
                    "off": "#8fbaf0"}[state]
            return fill, "white"
        if self.kind == "secondary":
            fill = {"normal": GREY_BTN, "hover": GREY_HOVER, "press": "#d1d1d6",
                    "off": GREY_BTN}[state]
            return fill, TEXT if state != "off" else TEXT3
        return None, BLUE if state != "off" else TEXT3

    def _paint(self, state):
        fill, fg = self._colors(state)
        if fill is None:  # lien : texte seul, souligné au survol
            self.config(image="", fg=fg, padx=0, pady=px(4),
                        font=self.font_ul if state == "hover" else self.font_obj)
            return
        self.img = rounded_image(self.w, self.h, self.h // 2, fill, bg=self.bg_parent)
        self.config(image=self.img, fg=fg, width=self.w, height=self.h)

    def _click(self, _):
        if not self.enabled:
            return
        self._paint("hover")
        self.command()

    def set_enabled(self, on, text=None):
        self.enabled = on
        if text:
            self.config(text=text)
        self.config(cursor="hand2" if on else "watch")
        self._paint("normal" if on else "off")


class Card(tk.Canvas):
    """Carte blanche arrondie ; on place les widgets dans .inner."""

    def __init__(self, parent, width, pad=20, radius=16, bg=BG):
        super().__init__(parent, width=width, height=10, bg=bg, bd=0, highlightthickness=0)
        self.cw, self.pad, self.radius, self.bg_parent = width, px(pad), px(radius), bg
        self.inner = tk.Frame(self, bg=CARD)
        self.win = self.create_window(self.pad, self.pad, window=self.inner, anchor="nw",
                                      width=width - 2 * self.pad)
        self.inner.bind("<Configure>", self._resize)

    def _resize(self, _):
        h = self.inner.winfo_reqheight() + 2 * self.pad
        self.config(height=h)
        self.img = rounded_image(self.cw, h, self.radius, CARD, outline=LINE, bg=self.bg_parent)
        self.delete("bgimg")
        self.create_image(0, 0, image=self.img, anchor="nw", tags="bgimg")
        self.tag_lower("bgimg")


class Field(tk.Canvas):
    """Champ de saisie arrondi, liseré bleu quand il a le focus."""

    def __init__(self, parent, width, font, textvariable, bg=BG):
        h = px(52)
        super().__init__(parent, width=width, height=h, bg=bg, bd=0, highlightthickness=0)
        self.w, self.h, self.bg_parent = width, h, bg
        self.entry = tk.Entry(self, textvariable=textvariable, font=font, bd=0,
                              highlightthickness=0, relief="flat", bg=CARD, fg=TEXT,
                              insertbackground=TEXT)
        self.create_window(px(18), h // 2, window=self.entry, anchor="w", width=width - px(36))
        self._paint(False)
        self.entry.bind("<FocusIn>", lambda _: self._paint(True))
        self.entry.bind("<FocusOut>", lambda _: self._paint(False))
        self.bind("<Button-1>", lambda _: self.entry.focus_set())

    def _paint(self, focus):
        self.img = rounded_image(self.w, self.h, px(12), CARD,
                                 outline=BLUE if focus else FIELD_LINE,
                                 width=2 if focus else 1, bg=self.bg_parent)
        self.delete("bgimg")
        self.create_image(0, 0, image=self.img, anchor="nw", tags="bgimg")
        self.tag_lower("bgimg")


class Activity(tk.Canvas):
    """Barre d'activité fine et animée (la durée d'un scan n'est pas connue)."""

    def __init__(self, parent, width, bg=BG):
        h = px(6)
        super().__init__(parent, width=width, height=h, bg=bg, bd=0, highlightthickness=0)
        self.w, self.h, self.x, self.running = width, h, 0, False
        self.track = rounded_image(width, h, h // 2, LINE, bg=bg)
        self.seg_w = width // 4
        self.seg = rounded_image(self.seg_w, h, h // 2, BLUE, bg=LINE)
        self.create_image(0, 0, image=self.track, anchor="nw")
        self.bar = self.create_image(-self.seg_w, 0, image=self.seg, anchor="nw")

    def start(self):
        self.running = True
        self._step()

    def _step(self):
        if not self.running or not self.winfo_exists():
            return
        self.x = (self.x + px(6)) % (self.w + self.seg_w)
        self.coords(self.bar, self.x - self.seg_w, 0)
        self.after(16, self._step)

    def stop(self):
        self.running = False


def badge(parent, text, size, fill, fg="white", font=None, bg=CARD):
    """Pastille ronde (numéro d'étape, coche)."""
    im = rounded_image(size, size, size // 2, fill, bg=bg)
    l = tk.Label(parent, image=im, text=text, compound="center", fg=fg, bg=bg, bd=0,
                 font=font)
    l.img = im
    return l


class CornerPicker(tk.Canvas):
    """Planche affichée en entier ; l'utilisatrice clique les 4 coins d'une photo.
    Une loupe suit la souris pour viser précisément ; les coins posés restent
    déplaçables à la souris. on_change(n) est appelé quand le nombre de coins change."""

    LOUPE = 170      # côté de la loupe (px écran, avant mise à l'échelle)
    ZOOM = 4         # grossissement de la loupe par rapport à l'affichage

    def __init__(self, parent, img_bgr, max_w, max_h, boxes=(), on_change=None, bg=BG):
        import cv2
        self.cv2 = cv2
        self.full = img_bgr
        h, w = img_bgr.shape[:2]
        self.k = min(max_w / w, max_h / h)          # échelle affichage / image
        self.dw, self.dh = int(w * self.k), int(h * self.k)
        super().__init__(parent, width=self.dw, height=self.dh, bg=bg, bd=0,
                         highlightthickness=0, cursor="crosshair")
        rgb = cv2.cvtColor(cv2.resize(img_bgr, (self.dw, self.dh), interpolation=cv2.INTER_AREA),
                           cv2.COLOR_BGR2RGB)
        self.base = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.create_image(0, 0, image=self.base, anchor="nw")
        for b in boxes:  # cadres déjà détectés, en discret
            self.create_polygon([c * self.k for p in b for c in p], outline="#c7c7cc",
                                fill="", width=1, dash=(4, 3))
        self.pts, self.drag, self.on_change = [], None, on_change
        self.ls = px(self.LOUPE)
        self.bind("<Motion>", self._move)
        self.bind("<Leave>", lambda _: self.delete("loupe"))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda _: setattr(self, "drag", None))

    # --- coins ---
    def _near(self, x, y):
        for i, (px_, py_) in enumerate(self.pts):
            if (px_ - x) ** 2 + (py_ - y) ** 2 <= px(12) ** 2:
                return i
        return None

    def _press(self, e):
        i = self._near(e.x, e.y)
        if i is not None:
            self.drag = i
        elif len(self.pts) < 4:
            self.pts.append((e.x, e.y))
            self._redraw()
            if self.on_change:
                self.on_change(len(self.pts))
        self._loupe(e.x, e.y)

    def _drag(self, e):
        if self.drag is not None:
            x = min(max(e.x, 0), self.dw - 1); y = min(max(e.y, 0), self.dh - 1)
            self.pts[self.drag] = (x, y)
            self._redraw()
            self._loupe(x, y)

    def _move(self, e):
        self._loupe(e.x, e.y)
        self.config(cursor="fleur" if self._near(e.x, e.y) is not None else "crosshair")

    def reset(self):
        self.pts = []
        self._redraw()
        if self.on_change:
            self.on_change(0)

    def _ordered(self):
        """Coins dans l'ordre haut-gauche, haut-droit, bas-droit, bas-gauche."""
        import numpy as np
        p = np.array(self.pts, float)
        c = p.mean(0)
        ang = np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0])
        p = p[np.argsort(ang)]                     # tri autour du centre
        start = np.argmin(p.sum(1))                # le plus haut-gauche d'abord
        return np.roll(p, -start, axis=0)

    def _redraw(self):
        self.delete("sel")
        if len(self.pts) == 4:
            q = self._ordered()
            self.create_polygon([c for p in q for c in p], outline=BLUE, fill="",
                                width=px(2), tags="sel")
        elif len(self.pts) > 1:
            self.create_line([c for p in self.pts for c in p], fill=BLUE, width=px(2),
                             dash=(6, 4), tags="sel")
        r = px(7)
        for i, (x, y) in enumerate(self.pts):
            self.create_oval(x - r, y - r, x + r, y + r, fill="white", outline=BLUE,
                             width=px(2), tags="sel")

    def quad_full(self):
        """Les 4 coins ordonnés, en pixels de l'image d'origine."""
        return self._ordered() / self.k

    # --- loupe ---
    def _loupe(self, x, y):
        self.delete("loupe")
        cv2 = self.cv2
        half = self.ls / (2 * self.ZOOM * self.k)   # demi-côté de la zone, en px image
        fx, fy = x / self.k, y / self.k
        h, w = self.full.shape[:2]
        x0, y0 = int(fx - half), int(fy - half)
        x1, y1 = int(fx + half), int(fy + half)
        pad = [max(0, -y0), max(0, y1 - h), max(0, -x0), max(0, x1 - w)]
        crop = self.full[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]
        if crop.size == 0:
            return
        crop = cv2.copyMakeBorder(crop, *pad, cv2.BORDER_CONSTANT, value=(245, 245, 247))
        crop = cv2.cvtColor(cv2.resize(crop, (self.ls, self.ls),
                                       interpolation=cv2.INTER_LINEAR), cv2.COLOR_BGR2RGB)
        im = Image.fromarray(crop)
        d = ImageDraw.Draw(im)
        c = self.ls // 2
        for off in (-1, 1):  # croix de visée, contour blanc + trait bleu
            d.line((c + off, 0, c + off, self.ls), fill="white")
            d.line((0, c + off, self.ls, c + off), fill="white")
        d.line((c, 0, c, self.ls), fill=_hex(BLUE))
        d.line((0, c, self.ls, c), fill=_hex(BLUE))
        d.rectangle((0, 0, self.ls - 1, self.ls - 1), outline=_hex(TEXT), width=2)
        self.loupe_img = ImageTk.PhotoImage(im)
        # la loupe se place en haut à droite du curseur, ou de l'autre côté près des bords
        g = px(24)
        lx = x + g if x + g + self.ls < self.dw else x - g - self.ls
        ly = y - g - self.ls if y - g - self.ls > 0 else y + g
        self.create_image(lx, ly, image=self.loupe_img, anchor="nw", tags="loupe")
