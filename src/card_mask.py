"""Isolamento della sticky card (gialla) dentro la cella di griglia.

La card e' incollata a mano: puo' essere leggermente ruotata e non riempie
tutta la cella. Il colore giallo saturo e' molto distante dal bianco del
foglio e dal nero della griglia, quindi una maschera HSV sul giallo isola
in modo affidabile i pixel di card indipendentemente da rotazione/offset.
"""
import numpy as np
from PIL import Image
from scipy import ndimage


def not_white_mask(rgb: np.ndarray) -> np.ndarray:
    """rgb: array HxWx3 uint8. Ritorna maschera booleana pixel-di-card.

    Il giallo saturo E i depositi rossi/scuri sono entrambi ben distinti dal
    bianco del foglio: si usa "non bianco" invece di "giallo" per evitare che
    le macchie di deposito (rosso scuro, non giallo) creino buchi nella
    maschera della card proprio dove servono per l'analisi.
    """
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    white = (r > 225) & (g > 225) & (b > 210)
    return ~white


def extract_card(rgb_crop: np.ndarray):
    """Da un ritaglio (cella card, con margini bianchi) estrae:
    - maschera booleana della card (piu' grande componente connessa non-bianca,
      buchi interni chiusi)
    - bounding box (l, t, r, b) relativo al crop
    """
    mask = not_white_mask(rgb_crop)
    lbl, n = ndimage.label(mask)
    if n == 0:
        raise ValueError("Nessuna regione non bianca trovata nella cella: card non individuata")
    sizes = ndimage.sum(mask, lbl, index=np.arange(1, n + 1))
    biggest = 1 + int(np.argmax(sizes))
    card_mask = ndimage.binary_fill_holes(lbl == biggest)
    ys, xs = np.where(card_mask)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return card_mask, box
