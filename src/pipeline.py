import csv

import numpy as np
from PIL import Image

from geometry import locate_cells
from card_mask import extract_card
from label_ocr import read_label
from deposit_metrics import analyze_card, DEFAULT_DPI

# Volume di applicazione (L/ha) usato nelle prove di riferimento.
DEFAULT_DROP_SIZE = 200

CSV_FIELDS = [
    "HEIGHT",
    "PLANT",
    "REPLICA",
    "SIDE",
    "DIRECTION",
    "TEST",
    "DROP SIZE",
    "DV01",
    "DV05",
    "DV09",
    "COVERAGE",
    "IMAGE AREA",
    "TOTAL DEPOSIT",
    "DROP DENSITY",
    "µL",
    "quality_flag",
    "label_ok",
    "label_raw_text",
    "source_file",
    "card_index",
]


def process_sheet(image_path: str, dpi: float = DEFAULT_DPI, drop_size=DEFAULT_DROP_SIZE) -> list:
    image = Image.open(image_path)
    cells = locate_cells(image_path)

    rows = []
    for cell in cells:
        card_crop = image.crop(cell.card_box).convert("RGB")
        card_rgb = np.array(card_crop)
        card_mask, _box = extract_card(card_rgb)

        label = read_label(image, cell.label_box)

        metrics = analyze_card(card_rgb, card_mask, dpi=dpi)

        row = {
            "HEIGHT": label.get("height"),
            "PLANT": label.get("plant"),
            "REPLICA": label.get("replica"),
            "SIDE": label.get("side"),
            "DIRECTION": label.get("direction"),
            "TEST": label.get("test"),
            # Volume di applicazione del trattamento (L/ha): metadato
            # sperimentale, non ricavabile dall'immagine.
            "DROP SIZE": drop_size,
            "DV01": round(metrics["dv01_um"], 1),
            "DV05": round(metrics["dv05_um"], 1),
            "DV09": round(metrics["dv09_um"], 1),
            "COVERAGE": round(metrics["coverage_pct"], 2),
            "IMAGE AREA": round(metrics["image_area_cm2"], 2),
            "TOTAL DEPOSIT": metrics["total_deposit_counted"],
            "DROP DENSITY": round(metrics["deposits_per_cm2"], 1),
            "µL": round(metrics["ul_cm2"], 3),
            "quality_flag": metrics["quality_flag"],
            "label_ok": label["ok"],
            "label_raw_text": label["raw_text"],
            "source_file": image_path,
            "card_index": cell.row_index + 1,
        }
        rows.append(row)

    return rows


def write_csv(rows: list, out_path: str):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
