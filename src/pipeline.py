import csv

import numpy as np
from PIL import Image

from geometry import locate_cells
from card_mask import extract_card
from label_ocr import read_label
from deposit_metrics import analyze_card, DEFAULT_DPI

CSV_FIELDS = [
    "source_file",
    "card_index",
    "Height",
    "Plant",
    "Replica",
    "Side",
    "Direction",
    "Test",
    "Coverage",
    "Image area",
    "Total deposit counted",
    "Deposits/cm2",
    "DV01",
    "DV05",
    "DV09",
    "uL/cm2",
    "quality_flag",
    "label_ok",
    "label_raw_text",
]


def process_sheet(image_path: str, dpi: float = DEFAULT_DPI) -> list:
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
            "source_file": image_path,
            "card_index": cell.row_index + 1,
            "Height": label.get("height"),
            "Plant": label.get("plant"),
            "Replica": label.get("replica"),
            "Side": label.get("side"),
            "Direction": label.get("direction"),
            "Test": label.get("test"),
            "Coverage": round(metrics["coverage_pct"], 2),
            "Image area": round(metrics["image_area_cm2"], 2),
            "Total deposit counted": metrics["total_deposit_counted"],
            "Deposits/cm2": round(metrics["deposits_per_cm2"], 1),
            "DV01": round(metrics["dv01_um"], 1),
            "DV05": round(metrics["dv05_um"], 1),
            "DV09": round(metrics["dv09_um"], 1),
            "uL/cm2": round(metrics["ul_cm2"], 3),
            "quality_flag": metrics["quality_flag"],
            "label_ok": label["ok"],
            "label_raw_text": label["raw_text"],
        }
        rows.append(row)

    return rows


def write_csv(rows: list, out_path: str):
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
