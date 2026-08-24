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
ROW_GAP = 3              # righe vuote che separano due fasce orizzontali
SPECK_INK_FRAC = 0.05    # inchiostro minimo di una fascia, sul massimo
LINE_HEIGHT_FRAC = 0.5   # altezza, sul ritaglio, oltre cui e' una linea
MAX_HEIGHT_RATIO = 2.0   # altezza, sulla mediana, oltre cui non e' un carattere
MIN_GLYPH_FILL = 0.15    # inchiostro minimo dentro il riquadro del glifo


def _drop_specks(ink: np.ndarray) -> np.ndarray:
    """Azzera i granelli di sporco della scansione.

    Le fasce orizzontali con pochissimo inchiostro (puntini di polvere sopra o
    sotto il testo) vanno tolte prima di ritagliare i caratteri: cadendo nelle
    stesse colonne di un carattere ne allungherebbero il bounding box, e il
    glifo normalizzato uscirebbe schiacciato e irriconoscibile (es. un `2`
    letto come `1`).
    """
    per_row = ink.sum(axis=1)
    rows = np.where(per_row > 0)[0]
    if len(rows) == 0:
        return ink

    bands, start, prev = [], rows[0], rows[0]
    for y in rows[1:]:
        if y - prev > ROW_GAP:
            bands.append((start, prev))
            start = y
        prev = y
    bands.append((start, prev))

    weights = [per_row[a:b + 1].sum() for a, b in bands]
    floor = SPECK_INK_FRAC * max(weights)
    out = np.zeros_like(ink)
    for (a, b), weight in zip(bands, weights):
        if weight >= floor:
            out[a:b + 1] = ink[a:b + 1]
    return out


def _drop_grid_lines(ink: np.ndarray) -> np.ndarray:
    """Azzera le colonne occupate da una linea della griglia.

    Su un foglio storto la linea verticale della tabella sconfina nel ritaglio
    dell'etichetta. Segmentata insieme al testo diventa un carattere in piu' in
    testa alla riga (e sposta di uno tutte le posizioni del prefisso), oppure
    si attacca alla prima lettera e la rende irriconoscibile. La linea si
    distingue dal testo perche' e' alta quanto tutto il ritaglio, mentre un
    carattere ne occupa un decimo.
    """
    tall = ink.sum(axis=0) > LINE_HEIGHT_FRAC * ink.shape[0]
    if not tall.any():
        return ink
    out = ink.copy()
    out[:, tall] = False
    return out


def segment_glyphs(gray: np.ndarray) -> list:
    """Da un ritaglio dell'etichetta ritorna la lista dei glifi (array bool),
    da sinistra a destra."""
    ink = _drop_specks(_drop_grid_lines(gray < INK_THRESHOLD))
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

    boxes = []
    for x0, x1 in spans:
        if x1 - x0 + 1 < MIN_GLYPH_WIDTH:
            continue
        sub = ink[:, x0:x1 + 1]
        if sub.sum() < MIN_GLYPH_INK:
            continue
        rows = np.where(sub.any(axis=1))[0]
        boxes.append((x0, x1, int(rows.min()), int(rows.max())))

    glyphs = [ink[top:bot + 1, x0:x1 + 1] for x0, x1, top, bot in _clip_tall(boxes)]
    # un carattere riempie da un terzo a meta' del suo riquadro; quel che resta
    # di una linea tagliata alla fascia del testo e' un tratto sottile e vuoto
    return [g for g in glyphs if g.mean() >= MIN_GLYPH_FILL]


def _clip_tall(boxes: list) -> list:
    """Riporta alla fascia del testo i glifi che ne escono in altezza.

    Il testo e' monospace e tutti i caratteri hanno la stessa altezza: quello
    che ne e' alto il doppio ha preso dentro qualcos'altro, di solito la linea
    della griglia di un foglio storto, che attraversa il ritaglio in diagonale
    e quindi sfugge a `_drop_grid_lines`. Il glifo si taglia alla fascia in cui
    stanno tutti gli altri invece di scartarlo: sotto la linea c'e' un
    carattere vero, e buttarlo via sposterebbe di uno tutte le posizioni del
    prefisso, facendo uscire un'etichetta sbagliata ma plausibile.
    """
    if len(boxes) < 2:
        return boxes
    heights = [bot - top + 1 for _x0, _x1, top, bot in boxes]
    limit = MAX_HEIGHT_RATIO * float(np.median(heights))
    band_top = int(np.median([top for _x0, _x1, top, _bot in boxes]))
    band_bot = int(np.median([bot for _x0, _x1, _top, bot in boxes]))

    out = []
    for x0, x1, top, bot in boxes:
        if bot - top + 1 > limit:
            top, bot = max(top, band_top), min(bot, band_bot)
            if bot <= top:
                continue
        out.append((x0, x1, top, bot))
    return out


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
