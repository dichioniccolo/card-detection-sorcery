"""Calcolo metriche di deposito su una singola card.

Pipeline: RGB card -> 8-bit media non pesata (R+G+B)/3 -> threshold 127
(deposito = pixel < 127) -> componenti connesse (8-connettivita', area >= 3 px)
-> metriche, calcolate sul RETTANGOLO che contiene la card.

Stato di validazione sui 24 casi di riferimento:
- Conversione 8-bit: CONFERMATA sul dato reale. Le mediane della mia
  conversione riproducono quelle degli screenshot 8-bit di DepositScan sugli
  8 casi disponibili (158/158, 159/159.3, 161/161.3, ...). ImageJ, di cui
  DepositScan e' una macro, usa la media non pesata dei canali.
- Image area = area del BOUNDING BOX della card a 600 DPI: CONFERMATA
  (es. 22.85 vs 22.87, 24.54 vs 24.80, 21.62 vs 21.77 cm2). DepositScan
  analizza una ROI rettangolare, non la sagoma ritagliata della card.
- Coverage = pixel deposito / pixel del bounding box: CONFERMATA, errore
  medio 0.22pp su 22 card (esclusi i 2 casi anomali sotto).
- MIN_COMPONENT_PX = 3: valore che azzera il bias sul conteggio
  (+0.02%, MAE 0.81%). Corrisponde al parametro "Size" di Analyze Particles.
- Deposits/cm2 = Total deposit / Image area: esatta.

LIMITE NOTO: 2 card di PROVA_A_0030 (H3 V DW A, H4 V DW A) hanno un forte
gradiente di illuminazione nella scansione; lo sfondo giallo scende sotto 127
e il Coverage risulta molto sovrastimato (40.3 vs 14.8, 38.6 vs 8.5). Il
conteggio dei depositi resta invece nella norma. Non e' stata introdotta
alcuna correzione: sono scansioni da rifare o da trattare a parte.

- DV01/DV05/DV09 e uL/cm2: NON CONFERMATI. DepositScan applica una
  trasformazione macchia->goccia (spread factor) ancora sconosciuta (vedi
  report Fase 2, sez. G). I valori qui prodotti sono una stima diagnostica
  (diametro equivalente della macchia trattato come diametro goccia, nessuna
  correzione di spread factor) e vanno considerati PROVVISORI fino
  all'esperimento di calibrazione.
"""
import numpy as np
from scipy import ndimage

MIN_COMPONENT_PX = 3
DEFAULT_DPI = 600.0


def to_gray(rgb: np.ndarray) -> np.ndarray:
    """Conversione RGB -> 8-bit con media NON pesata dei canali.

    E' la conversione di default di ImageJ (DepositScan e' una macro ImageJ):
    ImageJ usa (R+G+B)/3 a meno che non sia attiva l'opzione "weighted RGB
    conversions". Sulla card gialla la differenza rispetto alla luminanza
    ITU-R 601 e' molto grande (giallo: media ~168 vs luminanza ~208) e sposta
    l'esito del threshold 127 in modo determinante.

    Verificato direttamente contro gli screenshot 8-bit di DepositScan: le
    mediane coincidono sugli 8 casi disponibili (vedi docstring del modulo).
    """
    # cast a float PRIMA della somma: su uint8 r+g+b va in overflow (mod 256)
    arr = rgb.astype(np.float64)
    return (arr[..., 0] + arr[..., 1] + arr[..., 2]) / 3.0


def analyze_card(rgb_crop: np.ndarray, card_mask: np.ndarray, dpi: float = DEFAULT_DPI) -> dict:
    # DepositScan analizza una ROI RETTANGOLARE: tutte le metriche sono
    # riferite al bounding box della card, non alla sua sagoma ritagliata.
    ys, xs = np.where(card_mask)
    top, bot = int(ys.min()), int(ys.max()) + 1
    left, right = int(xs.min()), int(xs.max()) + 1

    gray = to_gray(rgb_crop)[top:bot, left:right]
    deposit_mask = gray < 127

    roi_px = deposit_mask.size
    deposit_px = int(deposit_mask.sum())
    coverage_pct = deposit_px / roi_px * 100.0

    lbl, n = ndimage.label(deposit_mask, structure=np.ones((3, 3)))
    if n > 0:
        sizes = ndimage.sum(deposit_mask, lbl, index=np.arange(1, n + 1))
        component_areas_px = sizes[sizes >= MIN_COMPONENT_PX]
    else:
        component_areas_px = np.array([])
    total_deposit_counted = int(len(component_areas_px))

    px_per_cm = dpi / 2.54
    image_area_cm2 = roi_px / (px_per_cm ** 2)
    deposits_per_cm2 = total_deposit_counted / image_area_cm2 if image_area_cm2 > 0 else float("nan")

    dv01, dv05, dv09, ul_cm2 = _volumetric_estimate(component_areas_px, image_area_cm2, roi_px)

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
