"""Lettura OCR dell'etichetta associata a ciascuna card.

L'etichetta e' testo monospace nero-su-bianco, posizione nota (vedi
geometry.py). L'OCR e' fatto SOLO sul ritaglio dell'etichetta, mai
sull'intero foglio. Il whitelist di caratteri elimina le confusioni piu'
comuni di Tesseract su questo font (1/l, 0/O).
"""
import re

import numpy as np
import pytesseract
from PIL import Image

_TESS_CONFIG = "--psm 7 -c tessedit_char_whitelist=HPRMVUDWABC0123456789"

_LABEL_RE = re.compile(
    r"H(?P<height>\d+)P(?P<plant>\d+)R(?P<replica>\d+)"
    r"(?P<side>[MV])(?P<direction>UP|DW)(?P<test>[A-D])"
)


def _ocr(img: Image.Image) -> str:
    return pytesseract.image_to_string(img, config=_TESS_CONFIG)


def read_label(image: Image.Image, label_box: tuple) -> dict:
    base = image.crop(label_box).convert("L")
    w, h = base.size

    # Nessuna singola scala risolve tutti i casi (dipende da come cade
    # l'antialiasing sul singolo carattere "1"): si provano piu' scale in
    # sequenza e si accetta il primo risultato che rispetta il pattern noto
    # dell'etichetta.
    attempts = []
    for scale in (1, 2, 3):
        img = base if scale == 1 else base.resize((w * scale, h * scale), Image.LANCZOS)
        attempts.append(img)
        arr = np.array(img)
        attempts.append(Image.fromarray(np.where(arr < 180, 0, 255).astype(np.uint8)))

    raw_text, compact, m = "", "", None
    for img in attempts:
        raw_text = _ocr(img)
        compact = re.sub(r"\s+", "", raw_text)
        m = _LABEL_RE.fullmatch(compact)
        if m:
            break

    if not m:
        return {
            "ok": False,
            "raw_text": raw_text.strip(),
            "compact_text": compact,
        }
    d = m.groupdict()
    return {
        "ok": True,
        "raw_text": raw_text.strip(),
        "height": int(d["height"]),
        "plant": int(d["plant"]),
        "replica": int(d["replica"]),
        "side": d["side"],
        "direction": d["direction"],
        "test": d["test"],
    }
