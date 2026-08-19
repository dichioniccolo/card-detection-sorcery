"""Calcolo metriche di deposito su una singola card.

Le formule sono state ricavate dal BYTECODE del plugin DepositScan
(`plugins/Java program/`: Water_Paper_Analysis.class, DropResultsFrame.class,
DropResultsFrame$DropRecord.class), non ipotizzate. Riferimenti al sorgente
nei commenti qui sotto.

Catena, come nel plugin:

    area       = pixelArea * 42.3333 * 42.3333       // px -> um^2
    ds         = sqrt(1.2732395447351628 * area)     // = sqrt(4A/pi)
    actualSize = 0.95 * pow(ds, 0.91)                // spread factor
    volume     = pi * pow(actualSize, 3.0) / 6.0     // um^3

Pubblicate anche in Zhu H., Salyani M., Fox R.D. (2011), "A portable scanning
system for evaluation of spray deposit distribution", Computers and
Electronics in Agriculture 76(1), 38-43; costanti dello spread factor da
Salyani & Fox (1994).
"""
import numpy as np
from scipy import ndimage

DEFAULT_DPI = 600.0

# DropResultsFrame.PIXEL_TO_UM: costante 42.3333, cablata nel plugin.
# Corrisponde a 25400/600, quindi DepositScan assume sempre 600 dpi.
PIXEL_TO_UM_AT_600DPI = 42.3333

# DropRecord.<init>: ldc2_w 1.2732395447351628 == 4/pi
FOUR_OVER_PI = 1.2732395447351628

# DropRecord.<init>: actualSize = 0.95 * pow(ds, 0.91)
SPREAD_A = 0.95
SPREAD_B = 0.91

# DropResultsFrame.<init> riga 531/581: i record entrano nell'analisi solo se
# actualSize > 50.0 um. Non e' un filtro in pixel: a 600 dpi equivale a
# scartare le particelle di 1-2 px (2 px -> 43.97 um, 3 px -> 52.84 um).
MIN_ACTUAL_DIAMETER_UM = 50.0

# Controllo qualita' NOSTRO, non di DepositScan. Lo sfondo collassato sotto la
# soglia (scansioni con gradiente di illuminazione) si riconosce da DUE segnali
# insieme; da solo nessuno dei due basta.
#
# 1. un singolo oggetto occupa piu' di MAX_COMPONENT_FRAC della ROI.
#    Sui 24 casi di riferimento: degradate 26.2-28.2%, la piu' alta tra le
#    valide 4.5%. Ma su card molto bagnate le gocce si fondono in una macchia
#    unica legittima, che da sola farebbe scattare il flag a vuoto.
# 2. il livello di sfondo della carta scende vicino alla soglia di 127.
#    Misurato come percentile basso dei massimi locali (vedi _background_floor):
#    degradate 136-138, la piu' bassa tra le valide 147.
#
# La soglia 143 sta in mezzo ai due gruppi. Alzarla rende il controllo piu'
# aggressivo, abbassarla piu' permissivo.
MAX_COMPONENT_FRAC = 0.10
MIN_BACKGROUND_GRAY = 143.0

# Il fondo si misura sui massimi di blocchi di questo lato (px a 600 dpi): in
# un blocco di carta pulita il massimo e' la carta, e anche in un blocco quasi
# tutto deposito resta qualche pixel di fondo. Il percentile scarta i blocchi
# interamente coperti dal deposito, che darebbero un falso fondo scuro.
BG_BLOCK_PX = 64
BG_FLOOR_PCTL = 5.0


def to_gray(rgb: np.ndarray) -> np.ndarray:
    """Conversione RGB -> 8-bit come ImageJ: media non pesata, arrotondata.

    ImageJ usa (r+g+b)/3 arrotondato all'intero piu' vicino, non la luminanza
    ITU-R 601. Sulla card gialla la differenza e' grande (media ~158 contro
    luminanza ~205) e cambia completamente l'esito della soglia a 127.

    Verificato contro gli screenshot 8-bit di DepositScan: le mediane
    coincidono su tutti e 8 i casi disponibili (158/158, 159/159.3, ...).
    """
    arr = rgb.astype(np.float64)
    return np.floor((arr[..., 0] + arr[..., 1] + arr[..., 2]) / 3.0 + 0.5)


def analyze_card(rgb_crop: np.ndarray, card_mask: np.ndarray, dpi: float = DEFAULT_DPI) -> dict:
    # Water_Paper_Analysis.run: ip.crop() sulla ROI, poi soglia e analisi.
    # DepositScan lavora quindi su un RETTANGOLO, non sulla sagoma della card.
    ys, xs = np.where(card_mask)
    top, bot = int(ys.min()), int(ys.max()) + 1
    left, right = int(xs.min()), int(xs.max()) + 1

    # Soglia inclusiva: in ImageJ l'intervallo di threshold comprende
    # l'estremo, quindi il livello 127 e' deposito.
    gray = to_gray(rgb_crop)[top:bot, left:right]
    deposit_mask = gray <= 127

    roi_px = deposit_mask.size
    um_per_px = PIXEL_TO_UM_AT_600DPI * (600.0 / dpi)
    roi_area_um2 = roi_px * um_per_px ** 2
    image_area_cm2 = roi_area_um2 / 1e8  # DropResultsFrame: / 100000000.0

    # ParticleAnalyzer(64, 1, rt, 0.0, MAX_VALUE, 0.0, 1.0): nessun filtro di
    # dimensione o circolarita' a questo stadio, 8-connettivita'.
    lbl, n = ndimage.label(deposit_mask, structure=np.ones((3, 3)))
    if n:
        sizes_px = ndimage.sum(deposit_mask, lbl, index=np.arange(1, n + 1))
    else:
        sizes_px = np.array([])

    areas_um2 = sizes_px * um_per_px ** 2
    ds_um = np.sqrt(FOUR_OVER_PI * areas_um2)
    actual_um = SPREAD_A * ds_um ** SPREAD_B

    keep = actual_um > MIN_ACTUAL_DIAMETER_UM
    areas_um2, actual_um = areas_um2[keep], actual_um[keep]

    total_deposit_counted = int(actual_um.size)
    # DropResultsFrame: coverage e conteggio si calcolano sui record TENUTI.
    coverage_pct = areas_um2.sum() / roi_area_um2 * 100.0 if roi_area_um2 else float("nan")
    deposits_per_cm2 = total_deposit_counted / image_area_cm2 if image_area_cm2 else float("nan")

    dv01, dv05, dv09, ul_cm2 = _volumetric(actual_um, areas_um2, roi_area_um2)

    largest_frac = float(sizes_px.max() / roi_px) if len(sizes_px) else 0.0
    bg_floor = _background_floor(gray)
    degraded = largest_frac > MAX_COMPONENT_FRAC and bg_floor < MIN_BACKGROUND_GRAY
    quality_flag = "SFONDO_SOTTO_SOGLIA" if degraded else "OK"

    return {
        "coverage_pct": coverage_pct,
        "image_area_cm2": image_area_cm2,
        "total_deposit_counted": total_deposit_counted,
        "deposits_per_cm2": deposits_per_cm2,
        "dv01_um": dv01,
        "dv05_um": dv05,
        "dv09_um": dv09,
        "ul_cm2": ul_cm2,
        "quality_flag": quality_flag,
        "largest_component_frac": largest_frac,
        "background_floor_gray": bg_floor,
    }


def _background_floor(gray: np.ndarray) -> float:
    """Livello di grigio della carta nella zona peggio illuminata della ROI.

    Massimo per blocchi (la carta e' il livello piu' chiaro localmente), poi un
    percentile basso di quei massimi: cosi' un blocco tutto coperto di deposito
    non viene scambiato per fondo scuro. Quando il valore si avvicina a 127 la
    carta stessa sta per finire sotto soglia.
    """
    h, w = gray.shape
    b = BG_BLOCK_PX
    if h < b or w < b:  # card troppo piccola per il campionamento a blocchi
        return float(gray.max())
    maxima = [
        gray[y:y + b, x:x + b].max()
        for y in range(0, h - b + 1, b)
        for x in range(0, w - b + 1, b)
    ]
    return float(np.percentile(maxima, BG_FLOOR_PCTL))


def _volumetric(actual_um, areas_um2, roi_area_um2):
    """DV01/DV05/DV09 (um) e uL/cm2, come DropResultsFrame."""
    if actual_um.size == 0 or roi_area_um2 <= 0:
        return float("nan"), float("nan"), float("nan"), float("nan")

    # Collections.sort con DropRecord.compareTo: area crescente.
    order = np.argsort(areas_um2, kind="stable")
    d = actual_um[order]

    volume = np.pi * d ** 3 / 6.0          # DropRecord: pi*pow(size,3)/6
    cumulative = np.cumsum(volume)
    pct = cumulative / cumulative[-1] * 100.0

    # DropResultsFrame.deposition = totalVolume * 0.1 / roiArea(um^2).
    # Equivale a (V um^3 / 1e9 uL) / (A um^2 / 1e8 cm^2).
    ul_cm2 = cumulative[-1] * 0.1 / roi_area_um2

    return _pct_value(d, pct, 10.0), _pct_value(d, pct, 50.0), _pct_value(d, pct, 90.0), ul_cm2


def _pct_value(d, pct, target):
    """DropResultsFrame.findPCTValue: diametro al percentile di volume."""
    j = int(np.searchsorted(pct, target))

    # Nessun punto sotto il target: il plugin interpola dall'origine, cioe'
    # sulla retta (0,0)-(pct[0], d[0]).
    if j == 0:
        return float(target * d[0] / pct[0]) if pct[0] else float(d[0])

    if j >= len(d):
        return float(d[-1])

    x0, x1 = pct[j - 1], pct[j]
    y0, y1 = d[j - 1], d[j]
    if x1 == x0:
        return float(y0)
    # (d2-d1)/(p2-p1) * (target-p1) + d1
    return float((y1 - y0) / (x1 - x0) * (target - x0) + y0)
