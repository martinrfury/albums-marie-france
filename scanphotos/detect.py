"""Détourage des tirages posés sur le capot blanc, quels que soient leurs formats.

1. Graines : zones fermées par des contours nets (le cœur de chaque photo).
2. Papier : contours faibles refermés largement, pour récupérer les bords blancs
   (Polaroïd, marges) ; le capot, blanc pur et lisse, en est exclu.
3. Chaque bloc de papier qui contient plusieurs graines (tirages posés bord à bord)
   est coupé en ligne droite là où le bord du papier est le plus marqué.
"""
import cv2
import numpy as np

H = 2000  # hauteur de travail (px)


def _k(n):
    return np.ones((n, n), np.uint8)


def _fill_closed(e, open_k=15):
    """Zones entièrement entourées de contours (le fond touche les bords de l'image)."""
    inv = (e == 0).astype(np.uint8)
    _, lab = cv2.connectedComponents(inv, connectivity=4)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    reg = (~np.isin(lab, list(border - {0}))).astype(np.uint8) * 255
    return cv2.morphologyEx(reg, cv2.MORPH_OPEN, _k(open_k))


def _comps(reg, min_area):
    cs, _ = cv2.findContours(reg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [c for c in cs if cv2.contourArea(c) > min_area]


def _split_block(block, boxes, edges):
    """Coupe droite récursive d'un bloc de papier entre groupes de graines."""
    if len(boxes) <= 1:
        return [block]
    best = None
    for axis in (0, 1):  # 0 : coupe horizontale, 1 : verticale
        lo_i, hi_i = (1, 3) if axis == 0 else (0, 2)
        order = sorted(boxes, key=lambda b: b[lo_i])
        prof = ((edges > 0) & block).sum(axis=1 - axis).astype(float)
        span = block.sum(axis=1 - axis).astype(float)
        frac = np.convolve(prof / np.maximum(span, 1), np.ones(3) / 3, "same")
        for n in range(1, len(order)):
            a, b = order[:n], order[n:]
            g0, g1 = max(x[hi_i] for x in a), min(x[lo_i] for x in b)
            if g1 - g0 < 2:
                continue
            pos = max(range(g0 + 1, g1), key=lambda p: frac[p])
            if best is None or frac[pos] > best[0]:
                best = (frac[pos], axis, pos, a, b)
    if best is None:
        return [block]
    _, axis, pos, a, b = best
    m1, m2 = block.copy(), block.copy()
    if axis == 0:
        m1[pos:] = False
        m2[:pos + 1] = False
    else:
        m1[:, pos:] = False
        m2[:, :pos + 1] = False
    return _split_block(m1, a, edges) + _split_block(m2, b, edges)


def order_quad(pts):
    """4 points -> ordre haut-gauche, haut-droit, bas-droit, bas-gauche."""
    p = np.asarray(pts, np.float32)
    c = p.mean(0)
    p = p[np.argsort(np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0]))]
    return np.roll(p, -int(np.argmin(p.sum(1))), axis=0)


def find_quads(img):
    """Image BGR d'une planche -> liste des 4 coins (px de l'image) de chaque photo,
    triée haut -> bas puis gauche -> droite."""
    s = img.shape[0] / H
    sm = cv2.resize(img, (round(img.shape[1] / s), H), interpolation=cv2.INTER_AREA)
    g = cv2.GaussianBlur(cv2.cvtColor(sm, cv2.COLOR_BGR2GRAY), (3, 3), 0)
    min_area = 0.01 * g.size

    # capot : quasi blanc pur et lisse (L >= 244) ; le papier, même blanc, est plus terne
    L = cv2.cvtColor(sm, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float32)
    mu = cv2.blur(L, (9, 9))
    std = np.sqrt(np.maximum(cv2.blur(L * L, (9, 9)) - mu * mu, 0))
    lid = cv2.morphologyEx(((mu >= 244) & (std < 3)).astype(np.uint8),
                           cv2.MORPH_OPEN, _k(7)) > 0
    lid[:8] = lid[-8:] = True          # liseré sombre des bords de la vitre :
    lid[:, :8] = lid[:, -8:] = True    # il relierait toutes les photos

    e1 = cv2.dilate(cv2.morphologyEx(cv2.Canny(g, 15, 40), cv2.MORPH_CLOSE, _k(5)), _k(3))
    sreg = _fill_closed(e1)
    sreg[lid] = 0
    seeds = _comps(cv2.morphologyEx(sreg, cv2.MORPH_OPEN, _k(15)), min_area)

    weak = cv2.Canny(g, 6, 18)
    paper = _fill_closed(cv2.morphologyEx(weak, cv2.MORPH_CLOSE, _k(21)), 21)
    paper[lid] = 0
    paper = cv2.morphologyEx(paper, cv2.MORPH_OPEN, _k(15))
    for c in seeds:
        cv2.drawContours(paper, [c], -1, 255, -1)

    n, comp = cv2.connectedComponents(paper)
    boxes = []
    for c in seeds:
        x, y, w, h = cv2.boundingRect(c)
        boxes.append((x, y, x + w, y + h, comp[y + h // 2, x + w // 2]))
    quads = []
    for lab in range(1, n):
        mine = [b[:4] for b in boxes if b[4] == lab]
        if not mine:
            continue
        for part in _split_block(comp == lab, mine, weak):
            m = cv2.morphologyEx(part.astype(np.uint8) * 255, cv2.MORPH_OPEN, _k(9))
            cs = _comps(m, min_area)
            if cs:
                quads.append(order_quad(cv2.boxPoints(cv2.minAreaRect(
                    max(cs, key=cv2.contourArea))) * s))
    quads.sort(key=lambda q: (round(q[:, 1].min() / (img.shape[0] / 8)), q[:, 0].min()))
    return quads


def crop_quad(img, quad, inset=4):
    """Redresse la photo délimitée par 4 coins (ordre quelconque)."""
    tl, tr, br, bl = order_quad(quad)
    w = int(round((np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2)) - 2 * inset
    h = int(round((np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2)) - 2 * inset
    src = np.float32([tl, tr, br, bl])
    dst = np.float32([[-inset, -inset], [w + inset, -inset],
                      [w + inset, h + inset], [-inset, h + inset]])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def split_photos(img):
    """Image BGR d'une planche -> liste des photos détourées."""
    return [crop_quad(img, q) for q in find_quads(img)]
