"""Rilevamento griglia foglio A4 e ritaglio delle 4 celle (card + etichetta).

Metodo (validato su 6 fogli reali, vedi report Fase 1/2):
- le linee della tabella prestampata sono l'elemento piu' stabile del foglio
- le righe orizzontali si rilevano in modo pulito guardando SOLO la striscia
  della colonna etichetta (sempre bianca, mai coperta dalla card incollata)
- le colonne verticali si rilevano guardando l'intera fascia verticale della
  tabella (bordo sx, divisore centrale, bordo dx)
"""
from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class Cell:
    row_index: int  # 0..3, top->bottom
    card_box: tuple  # (left, top, right, bottom) in pixel, immagine originale
    label_box: tuple


def _group(idxs, gap=5):
    if len(idxs) == 0:
        return []
    groups = []
    cur = [idxs[0]]
    for x in idxs[1:]:
        if x - cur[-1] <= gap:
            cur.append(x)
        else:
            groups.append(cur)
            cur = [x]
    groups.append(cur)
    return [int(np.mean(g)) for g in groups]


def detect_grid(gray: np.ndarray, dark_thresh: int = 100):
    """Ritorna (rows, cols): 5 y di linee orizzontale, 3 x di linee verticali."""
    h, w = gray.shape
    dark = gray < dark_thresh

    # colonna etichetta presunta nella meta' destra della pagina: usa una
    # finestra larga e permissiva, poi raffina una volta note le colonne.
    label_strip = dark[:, int(w * 0.55):int(w * 0.90)]
    row_frac = label_strip.mean(axis=1)
    rows = _group(np.where(row_frac > 0.6)[0])
    if len(rows) != 5:
        raise ValueError(f"Attese 5 linee orizzontali, trovate {len(rows)}: {rows}")

    top, bot = rows[0], rows[-1]
    col_frac = dark[top:bot, :].mean(axis=0)
    cols = _group(np.where(col_frac > 0.3)[0])
    if len(cols) != 3:
        raise ValueError(f"Attese 3 linee verticali, trovate {len(cols)}: {cols}")

    return rows, cols


def build_cells(rows, cols, margin: int = 8) -> list:
    """Da 5 righe + 3 colonne costruisce le 4 celle (card_box, label_box).

    margin: pixel di inset rispetto alle linee di griglia, per non includere
    il bordo nero della tabella nei ritagli.
    """
    left, mid, right = cols
    cells = []
    for i in range(4):
        y0, y1 = rows[i], rows[i + 1]
        card_box = (left + margin, y0 + margin, mid - margin, y1 - margin)
        label_box = (mid + margin, y0 + margin, right - margin, y1 - margin)
        cells.append(Cell(row_index=i, card_box=card_box, label_box=label_box))
    return cells


def locate_cells(image_path: str) -> list:
    im = Image.open(image_path)
    gray = np.array(im.convert("L"))
    rows, cols = detect_grid(gray)
    return build_cells(rows, cols)
