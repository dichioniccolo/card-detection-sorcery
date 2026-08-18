"""Segmentazione e normalizzazione dei caratteri dell'etichetta.

Condiviso tra la costruzione dei template (tools/build_label_templates.py) e
il riconoscimento a runtime (label_ocr.py), cosi' le due strade non possono
divergere.
"""
import numpy as np

GLYPH_SIZE = 32          # lato del glifo normalizzato
INK_THRESHOLD = 128      # sotto questo livello di grigio e' inchiostro
MIN_GLYPH_WIDTH = 12     # scarta le macchioline di rumore
MIN_GLYPH_INK = 40       # pixel di inchiostro minimi per un carattere
COLUMN_GAP = 8           # colonne vuote che separano due caratteri


def segment_glyphs(gray: np.ndarray) -> list:
    """Da un ritaglio dell'etichetta ritorna la lista dei glifi (array bool),
    da sinistra a destra."""
    ink = gray < INK_THRESHOLD
    cols = np.where(ink.any(axis=0))[0]
    if len(cols) == 0:
        return []

    spans = []
    start = prev = cols[0]
    for x in cols[1:]:
        if x - prev > COLUMN_GAP:
            spans.append((start, prev))
            start = x
        prev = x
    spans.append((start, prev))

    glyphs = []
    for x0, x1 in spans:
        if x1 - x0 + 1 < MIN_GLYPH_WIDTH:
            continue
        sub = ink[:, x0:x1 + 1]
        if sub.sum() < MIN_GLYPH_INK:
            continue
        rows = np.where(sub.any(axis=1))[0]
        glyphs.append(sub[rows.min():rows.max() + 1, :])
    return glyphs


def normalize_glyph(glyph: np.ndarray) -> np.ndarray:
    """Riscala un glifo a GLYPH_SIZE x GLYPH_SIZE, in float 0..1.

    Il riscalamento e' fatto per aree (media dei pixel di ogni blocco), quindi
    conserva l'informazione sui bordi senza dipendere da PIL.
    """
    h, w = glyph.shape
    ys = (np.arange(GLYPH_SIZE + 1) * h) // GLYPH_SIZE
    xs = (np.arange(GLYPH_SIZE + 1) * w) // GLYPH_SIZE
    out = np.zeros((GLYPH_SIZE, GLYPH_SIZE), dtype=np.float64)
    src = glyph.astype(np.float64)
    for i in range(GLYPH_SIZE):
        y0, y1 = ys[i], max(ys[i + 1], ys[i] + 1)
        for j in range(GLYPH_SIZE):
            x0, x1 = xs[j], max(xs[j + 1], xs[j] + 1)
            out[i, j] = src[y0:y1, x0:x1].mean()
    return out
