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


# Parametri di rilevamento della griglia. I default valgono per le scansioni di
# riferimento; il sweep permissivo (vedi locate_cells) li fa variare quando la
# griglia non viene trovata al primo colpo.
DARK_THRESH = 100
ROW_FRAC = 0.6
COL_FRAC = 0.3


def detect_grid(gray: np.ndarray, dark_thresh: int = DARK_THRESH,
                row_frac: float = ROW_FRAC, col_frac: float = COL_FRAC):
    """Ritorna (rows, cols): 5 y di linee orizzontale, 3 x di linee verticali."""
    h, w = gray.shape
    dark = gray < dark_thresh

    # colonna etichetta presunta nella meta' destra della pagina: usa una
    # finestra larga e permissiva, poi raffina una volta note le colonne.
    label_strip = dark[:, int(w * 0.55):int(w * 0.90)]
    frac = label_strip.mean(axis=1)
    rows = _group(np.where(frac > row_frac)[0])
    if len(rows) != 5:
        raise ValueError(f"Attese 5 linee orizzontali, trovate {len(rows)}: {rows}")

    top, bot = rows[0], rows[-1]
    frac = dark[top:bot, :].mean(axis=0)
    cols = _group(np.where(frac > col_frac)[0])
    if len(cols) != 3:
        raise ValueError(f"Attese 3 linee verticali, trovate {len(cols)}: {cols}")

    return rows, cols


# Sweep usato in modalita' permissiva: soglie piu' basse recuperano le griglie
# stampate chiare o scansionate slavate, quelle piu' alte i fogli con sporco o
# ombre che fanno trovare linee di troppo. Il primo insieme di parametri che da'
# esattamente 5 righe e 3 colonne vince.
_RELAXED_SWEEP = [
    (dark, row, col)
    for dark in (100, 120, 140, 160, 80, 60)
    for row in (0.6, 0.5, 0.4, 0.3, 0.7, 0.8)
    for col in (0.3, 0.25, 0.2, 0.15, 0.4, 0.5)
]


def detect_grid_relaxed(gray: np.ndarray):
    """detect_grid con sweep dei parametri. Ritorna (rows, cols, params_usati)."""
    errors = []
    for dark, row, col in _RELAXED_SWEEP:
        try:
            rows, cols = detect_grid(gray, dark_thresh=dark, row_frac=row, col_frac=col)
        except ValueError as e:
            errors.append(str(e))
            continue
        return rows, cols, (dark, row, col)
    # riporta l'esito coi parametri di default: e' il piu' informativo
    raise ValueError(
        f"griglia non trovata con nessuno dei {len(_RELAXED_SWEEP)} set di "
        f"parametri provati (col default: {errors[0] if errors else 'n/d'})"
    )


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


def locate_cells(image_path: str, relaxed: bool = False):
    """Ritorna (celle, nota). `nota` e' None se la griglia e' stata trovata coi
    parametri di default, altrimenti descrive quelli che hanno funzionato."""
    im = Image.open(image_path)
    gray = np.array(im.convert("L"))
    if not relaxed:
        return build_cells(*detect_grid(gray)), None
    try:
        return build_cells(*detect_grid(gray)), None
    except ValueError:
        rows, cols, params = detect_grid_relaxed(gray)
        note = ("griglia trovata con parametri permissivi "
                f"(dark_thresh={params[0]}, row_frac={params[1]}, col_frac={params[2]})")
        return build_cells(rows, cols), note
