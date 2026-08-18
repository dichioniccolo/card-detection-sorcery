"""Calcolo metriche di deposito su una singola card.

Pipeline: RGB card -> 8-bit (luminanza ITU-R 601, standard PIL 'L') ->
threshold 127 (deposito = pixel scuro, luminanza < 127) -> maschera binaria
-> componenti connesse -> metriche.

Stato di validazione (vedi report Fase 2, sez. C/D/E/F/G/H):
- Coverage: formula CONFERMATA quantitativamente (errore medio 0.24pp su 8
  card reali).
- Total deposit counted: formula base CONFERMATA approssimata (errore medio
  ~3.5%); il filtro dimensionale minimo esatto di DepositScan resta ignoto,
  qui si usa un filtro empirico (area >= 2 px) tarato sui casi reali.
- Deposits/cm2 e Image area: formula base CONFERMATA.
- DV01/DV05/DV09 e uL/cm2: NON CONFERMATI. DepositScan applica una
  trasformazione macchia->goccia (spread factor) ancora sconosciuta (vedi
  report Fase 2, sez. G). I valori qui prodotti sono una stima diagnostica
  (diametro equivalente della macchia trattato come diametro goccia, nessuna
  correzione di spread factor) e vanno considerati PROVVISORI fino
  all'esperimento di calibrazione.
"""
import numpy as np
from scipy import ndimage

MIN_COMPONENT_PX = 2
DEFAULT_DPI = 600.0


def to_gray(rgb: np.ndarray) -> np.ndarray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return 0.299 * r + 0.587 * g + 0.114 * b


def analyze_card(rgb_crop: np.ndarray, card_mask: np.ndarray, dpi: float = DEFAULT_DPI) -> dict:
    gray = to_gray(rgb_crop)
    deposit_mask = (gray < 127) & card_mask

    total_card_px = int(card_mask.sum())
    deposit_px = int(deposit_mask.sum())
    coverage_pct = deposit_px / total_card_px * 100.0

    lbl, n = ndimage.label(deposit_mask, structure=np.ones((3, 3)))
    if n > 0:
        sizes = ndimage.sum(deposit_mask, lbl, index=np.arange(1, n + 1))
        keep = sizes >= MIN_COMPONENT_PX
        component_areas_px = sizes[keep]
    else:
        component_areas_px = np.array([])
    total_deposit_counted = int(len(component_areas_px))

    px_per_cm = dpi / 2.54
    image_area_cm2 = total_card_px / (px_per_cm ** 2)
    deposits_per_cm2 = total_deposit_counted / image_area_cm2 if image_area_cm2 > 0 else float("nan")

    dv01, dv05, dv09, ul_cm2 = _volumetric_estimate(component_areas_px, image_area_cm2, total_card_px)

    return {
        "coverage_pct": coverage_pct,
        "image_area_cm2": image_area_cm2,
        "total_deposit_counted": total_deposit_counted,
        "deposits_per_cm2": deposits_per_cm2,
        "dv01_um": dv01,
        "dv05_um": dv05,
        "dv09_um": dv09,
        "ul_cm2": ul_cm2,
    }


def _volumetric_estimate(component_areas_px, image_area_cm2, total_card_px):
    """Stima DIAGNOSTICA e PROVVISORIA di DV01/05/09 e uL/cm2.

    Nessuna calibrazione spread-factor: tratta il diametro equivalente della
    macchia come diametro di goccia. Vedi docstring modulo.
    """
    if len(component_areas_px) == 0 or image_area_cm2 <= 0:
        return float("nan"), float("nan"), float("nan"), float("nan")

    cm2_per_px = image_area_cm2 / total_card_px
    areas_cm2 = component_areas_px * cm2_per_px
    diam_um = 2.0 * np.sqrt(areas_cm2 / np.pi) * 1e4  # cm -> um
    vol_um3 = (np.pi / 6.0) * diam_um ** 3

    order = np.argsort(diam_um)
    d_sorted = diam_um[order]
    v_sorted = vol_um3[order]
    cum_v = np.cumsum(v_sorted)
    total_v = cum_v[-1]
    cum_v_frac = cum_v / total_v

    def pct(p):
        idx = np.searchsorted(cum_v_frac, p)
        idx = min(idx, len(d_sorted) - 1)
        return float(d_sorted[idx])

    dv01, dv05, dv09 = pct(0.1), pct(0.5), pct(0.9)

    # uL/cm2: volume totale (um^3) -> uL (1 uL = 1e9 um^3), diviso area card
    total_v_ul = total_v / 1e9
    ul_cm2 = total_v_ul / image_area_cm2

    return dv01, dv05, dv09, ul_cm2
