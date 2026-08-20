"""Rilevamento griglia foglio A4 e ritaglio delle celle (card + etichetta).

Due formati di foglio, riconosciuti dall'orientamento della scansione:
- verticale: card una per riga, card a sinistra ed etichetta a destra;
- orizzontale: card una per colonna, card in alto ed etichetta in basso,
  col testo dell'etichetta ruotato.

Il numero di card per foglio non e' fissato: si prende quello che dice la
griglia, due o venti che siano.
Il foglio orizzontale viene ruotato di 90 gradi in senso antiorario: cosi'
torna nella stessa geometria di quello verticale (card a sinistra, etichetta a
destra, una card per riga) e tutto il resto della pipeline non cambia.

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
    row_index: int  # 0..n-1, top->bottom (dopo l'eventuale rotazione)
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


# Una cella piu' bassa di cosi' e' una linea rilevata due volte, non una card:
# a 600 DPI sono poco piu' di 2 cm, meno del lato corto di una sticky card.
MIN_CELL_PX = 500
# Sotto le due celle non e' una griglia: e' il bordo del foglio o un'ombra.
MIN_CELLS = 2


def _merge_close(lines, min_gap):
    """Fonde le linee troppo vicine per delimitare una cella vera."""
    out = []
    for y in lines:
        if out and y - out[-1] < min_gap:
            out[-1] = (out[-1] + y) // 2
            continue
        out.append(y)
    return out


# Parametri di rilevamento della griglia. I default valgono per le scansioni di
# riferimento; il sweep permissivo (vedi locate_cells) li fa variare quando la
# griglia non viene trovata al primo colpo.
DARK_THRESH = 100
ROW_FRAC = 0.6
COL_FRAC = 0.3


def detect_grid(gray: np.ndarray, dark_thresh: int = DARK_THRESH,
                row_frac: float = ROW_FRAC, col_frac: float = COL_FRAC):
    """Ritorna (rows, cols): le y delle linee orizzontali (una in piu' del
    numero di celle, quante che siano) e le 3 x di quelle verticali."""
    h, w = gray.shape
    dark = gray < dark_thresh

    # colonna etichetta presunta nella meta' destra della pagina: usa una
    # finestra larga e permissiva, poi raffina una volta note le colonne.
    label_strip = dark[:, int(w * 0.55):int(w * 0.90)]
    frac = label_strip.mean(axis=1)
    rows = _merge_close(_group(np.where(frac > row_frac)[0]), MIN_CELL_PX)
    if len(rows) < MIN_CELLS + 1:
        raise ValueError(
            f"Attese almeno {MIN_CELLS + 1} linee orizzontali, trovate {len(rows)}: {rows}")

    top, bot = rows[0], rows[-1]
    frac = dark[top:bot, :].mean(axis=0)
    cols = _group(np.where(frac > col_frac)[0])
    if len(cols) != 3:
        raise ValueError(f"Attese 3 linee verticali, trovate {len(cols)}: {cols}")

    return rows, cols


# Sweep usato in modalita' permissiva: soglie piu' basse recuperano le griglie
# stampate chiare o scansionate slavate, quelle piu' alte i fogli con sporco o
# ombre che fanno trovare linee di troppo. Il primo insieme di parametri che da'
# una griglia plausibile (almeno due celle e 3 colonne) vince.
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
    """Da n righe + 3 colonne costruisce le n-1 celle (card_box, label_box).

    margin: pixel di inset rispetto alle linee di griglia, per non includere
    il bordo nero della tabella nei ritagli.
    """
    left, mid, right = cols
    cells = []
    for i in range(len(rows) - 1):
        y0, y1 = rows[i], rows[i + 1]
        card_box = (left + margin, y0 + margin, mid - margin, y1 - margin)
        label_box = (mid + margin, y0 + margin, right - margin, y1 - margin)
        cells.append(Cell(row_index=i, card_box=card_box, label_box=label_box))
    return cells


def load_sheet(image_path: str):
    """Apre il foglio e lo porta in verticale.

    Le scansioni orizzontali (card in colonna, etichette ruotate) vengono
    girate di 90 gradi in senso antiorario: dopo la rotazione le etichette
    sono dritte e la griglia ha la stessa forma del foglio verticale.
    """
    im = Image.open(image_path)
    if im.width > im.height:
        return im.rotate(90, expand=True)
    return im


# Raddrizzamento delle scansioni storte. Basta mezzo grado perche' le linee
# della griglia si spalmino su una decina di righe di pixel e non superino piu'
# la soglia di copertura: la griglia risulta introvabile anche col sweep
# permissivo. L'angolo si cerca su una copia rimpicciolita (la deriva scala
# insieme all'immagine, e provare un centinaio di angoli a piena risoluzione
# costerebbe troppo).
DESKEW_MAX_DEG = 5.0
DESKEW_STEP_DEG = 0.1
DESKEW_SCALE = 4
DESKEW_TRIES = 5    # angoli migliori da riprovare a piena risoluzione


def _row_coverage(gray: np.ndarray, dark_thresh: int = DARK_THRESH) -> float:
    """Copertura della riga di pixel piu' scura nella striscia dell'etichetta.

    Vale 1.0 quando una linea della griglia e' perfettamente orizzontale, e
    cala rapidamente man mano che il foglio e' storto."""
    w = gray.shape[1]
    strip = (gray < dark_thresh)[:, int(w * 0.55):int(w * 0.90)]
    return float(strip.mean(axis=1).max())


def _skew_angles(image) -> list:
    """Angoli da provare, dal piu' promettente in giu'."""
    small = image.convert("L").reduce(DESKEW_SCALE)
    steps = int(round(DESKEW_MAX_DEG / DESKEW_STEP_DEG))
    scored = []
    for i in range(-steps, steps + 1):
        angle = round(i * DESKEW_STEP_DEG, 2)
        rotated = small if angle == 0 else small.rotate(
            angle, resample=Image.BILINEAR, fillcolor=255)
        scored.append((_row_coverage(np.array(rotated)), angle))
    scored.sort(key=lambda t: (-t[0], abs(t[1])))
    return [a for _score, a in scored if a != 0]


def _rotate(image, angle: float):
    return image.rotate(angle, resample=Image.BILINEAR, fillcolor="white")


def locate_cells(image, relaxed: bool = False):
    """Ritorna (immagine, celle, nota).

    L'immagine di ritorno e' quella su cui valgono le celle: e' quella di
    partenza, oppure una sua copia raddrizzata se il foglio era storto.
    `nota` e' None se la griglia e' stata trovata al primo colpo, altrimenti
    dice cosa e' servito per trovarla.
    """
    gray = np.array(image.convert("L"))
    try:
        return image, build_cells(*detect_grid(gray)), None
    except ValueError as e:
        # il nome legato da `except ... as` sparisce a fine blocco: va tenuto
        # da parte per rilanciarlo se anche il raddrizzamento non basta
        first_error = e

    # foglio storto: si raddrizza e si riprova coi parametri di default
    for angle in _skew_angles(image)[:DESKEW_TRIES]:
        straight = _rotate(image, angle)
        try:
            cells = build_cells(*detect_grid(np.array(straight.convert("L"))))
        except ValueError:
            continue
        # la rotazione reinterpola anche le card, non solo la griglia: le
        # metriche escono da un'immagine ricampionata, va detto
        return straight, cells, f"foglio storto, raddrizzato di {angle:+.1f} gradi"

    if not relaxed:
        raise first_error

    rows, cols, params = detect_grid_relaxed(gray)
    note = ("griglia trovata con parametri permissivi "
            f"(dark_thresh={params[0]}, row_frac={params[1]}, col_frac={params[2]})")
    return image, build_cells(rows, cols), note
