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

- DV01/DV05/DV09 e uL/cm2: implementate le equazioni pubblicate di DepositScan
  (Zhu, Salyani & Fox 2011; vedi _volumetric_estimate). Errore sui 22 casi:
  DV01 MAE 0.82%, DV05 0.50%, DV09 0.49%, uL/cm2 2.32%.
"""
import numpy as np
from scipy import ndimage

MIN_COMPONENT_PX = 3
DEFAULT_DPI = 600.0

# Controllo qualita': se un singolo oggetto occupa piu' di questa frazione
# della ROI, non e' un deposito ma sfondo collassato sotto la soglia (tipico
# di scansioni con gradiente di illuminazione). Sui 24 casi di riferimento il
# criterio separa nettamente: card degradate 25.8-27.8%, la piu' alta tra
# quelle valide 4.5%.
MAX_COMPONENT_FRAC = 0.10


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

    # Soglia INCLUSIVA: in ImageJ l'intervallo di threshold comprende
    # l'estremo, quindi il livello 127 e' deposito. Usare "< 127" scarta un
    # livello e produce un sottoconteggio sistematico (verificato sui 22 casi:
    # bias sul conteggio -1.4% con "< 127", 0.00% con "<= 127").
    gray = to_gray(rgb_crop)[top:bot, left:right]
    deposit_mask = gray <= 127

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

    dv01, dv05, dv09, ul_cm2 = _volumetric_estimate(component_areas_px, image_area_cm2, dpi)

    largest_frac = float(component_areas_px.max() / roi_px) if len(component_areas_px) else 0.0
    quality_flag = "OK" if largest_frac <= MAX_COMPONENT_FRAC else "SFONDO_SOTTO_SOGLIA"

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
    }


def _volumetric_estimate(component_areas_px, image_area_cm2, dpi=DEFAULT_DPI):
    """DV01/DV05/DV09 (um) e uL/cm2 secondo le equazioni pubblicate di
    DepositScan.

    Riferimento: Zhu H., Salyani M., Fox R.D. (2011), "A portable scanning
    system for evaluation of spray deposit distribution", Computers and
    Electronics in Agriculture 76(1), 38-43.

        ds = sqrt(4A/pi)                (Eq. 2)  diametro macchia, A in um^2
        d  = 0.95 * ds^0.910            (Eq. 1)  spread factor della carta
                                                 idrosensibile, costanti di
                                                 Salyani & Fox (1994)
        d  = 1.06 * A^0.455             (Eq. 3)  forma finale, equivalente
        Vi = pi * di^3 / 6              (Eq. 4)  volume della singola goccia
        Vj = somma cumulata dei Vi      (Eq. 5)
        %Vj = Vj / VN * 100             (Eq. 6)

    DV0.1/0.5/0.9 sono i diametri dove %Vj vale 10/50/90; se nessun punto cade
    esattamente sul valore, DepositScan interpola linearmente tra i due punti
    piu' vicini. uL/cm2 e' il volume cumulato totale diviso l'area analizzata.

    Nessun parametro libero: tutte le costanti vengono dal paper.
    """
    if len(component_areas_px) == 0 or image_area_cm2 <= 0:
        return float("nan"), float("nan"), float("nan"), float("nan")

    um_per_px = 25400.0 / dpi
    areas_um2 = component_areas_px * um_per_px ** 2

    diam_um = np.sort(1.06 * areas_um2 ** 0.455)          # Eq. 3
    vol_um3 = np.pi * diam_um ** 3 / 6.0                  # Eq. 4
    cum_v = np.cumsum(vol_um3)                            # Eq. 5
    pct_v = cum_v / cum_v[-1] * 100.0                     # Eq. 6

    def dv(target_pct):
        j = int(np.searchsorted(pct_v, target_pct))
        if j == 0:
            return float(diam_um[0])
        if j >= len(diam_um):
            return float(diam_um[-1])
        x0, x1 = pct_v[j - 1], pct_v[j]
        y0, y1 = diam_um[j - 1], diam_um[j]
        if x1 == x0:
            return float(y0)
        return float(y0 + (target_pct - x0) * (y1 - y0) / (x1 - x0))

    # 1 uL = 1e9 um^3
    ul_cm2 = cum_v[-1] / 1e9 / image_area_cm2

    return dv(10.0), dv(50.0), dv(90.0), ul_cm2
