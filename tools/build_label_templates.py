#!/usr/bin/env python3
"""Costruisce i template dei caratteri delle etichette a partire dai fogli di
riferimento, di cui conosciamo il testo esatto.

Le etichette sono stampate con un font monospace fisso e usano un alfabeto di
pochi caratteri, quindi il riconoscimento per template e' piu' affidabile di
un OCR generico e non richiede dipendenze esterne (niente tesseract).

Uso:
    venv/bin/python3 tools/build_label_templates.py
Scrive src/label_templates.npz
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from geometry import load_sheet, locate_cells  # noqa: E402
from label_glyphs import segment_glyphs, normalize_glyph  # noqa: E402

TRUTH = {
    "PROVA_A_0027.jpg": ["H1P1R1MUPA", "H1P1R1MDWA", "H2P1R1MUPA", "H2P1R1MDWA"],
    "PROVA_A_0030.jpg": ["H3P1R1VUPA", "H3P1R1VDWA", "H4P1R1VUPA", "H4P1R1VDWA"],
    "PROVA_B_0007.jpg": ["H1P1R1MUPB", "H1P1R1MDWB", "H2P1R1MUPB", "H2P1R1MDWB"],
    "PROVA_B_0009.jpg": ["H1P1R1VUPB", "H1P1R1VDWB", "H2P1R1VUPB", "H2P1R1VDWB"],
    "PROVA_C_0008.jpg": ["H3P1R1VUPC", "H3P1R1VDWC", "H4P1R1VUPC", "H4P1R1VDWC"],
    "PROVA_D_0016.jpg": ["H3P1R1VUPD", "H3P1R1VDWD", "H4P1R1VUPD", "H4P1R1VDWD"],
    # foglio orizzontale: 6 card, etichette lette dopo la rotazione
    # (dall'alto in basso una volta raddrizzato il foglio)
    "20260618_CNV01452120260619103843_0001.jpg": [
        "H1P1R1MUPCNV", "H1P1R1MDWCNV", "H2P1R1MUPCNV",
        "H2P1R1MDWCNV", "H3P1R1MUPCNV", "H3P1R1MDWCNV",
    ],
    # foglio "senza height/plant": etichette N/S/O/E <distanza> A, niente
    # prefisso H/P/R. Introduce le cifre 0 e 5 e le lettere S/O/E, assenti
    # dai fogli di riferimento precedenti.
    "senza-height-plant/DER_A014390_0001.jpg": [
        "N3A", "N5A", "N10A", "S3A", "S5A", "S10A",
    ],
    "senza-height-plant/DER_A014390_0002.jpg": [
        "O3A", "O5A", "O10A", "E3A", "E5A", "E10A",
    ],
}


def _load_existing():
    """Template gia' costruiti, usati come fallback per i fogli sorgente non
    piu' presenti in locale: senza, rigenerare perderebbe i loro caratteri."""
    path = ROOT / "src" / "label_templates.npz"
    if not path.exists():
        return {}
    data = np.load(path)
    return {c: t for c, t in zip(data["chars"], data["templates"])}


def main():
    samples = {}
    for fname, labels in TRUTH.items():
        path = ROOT / "assets" / fname if "/" in fname else ROOT / "assets" / "A" / fname
        if not path.exists():
            print(f"manca {path}, salto", file=sys.stderr)
            continue
        image = load_sheet(str(path))
        image, cells, _note = locate_cells(image, relaxed=True)
        for cell, text in zip(cells, labels):
            crop = np.array(image.crop(cell.label_box).convert("L"))
            glyphs = segment_glyphs(crop)
            if len(glyphs) != len(text):
                print(f"{fname} card {cell.row_index+1}: {len(glyphs)} glifi per "
                      f"{len(text)} caratteri ({text}), salto", file=sys.stderr)
                continue
            for g, ch in zip(glyphs, text):
                samples.setdefault(ch, []).append(normalize_glyph(g))

    if not samples:
        sys.exit("nessun campione raccolto")

    existing = _load_existing()
    chars = sorted(set(samples) | set(existing))
    templates = np.stack([
        np.mean(samples[c], axis=0) if c in samples else existing[c]
        for c in chars
    ])
    out = ROOT / "src" / "label_templates.npz"
    np.savez_compressed(out, chars=np.array(chars), templates=templates)

    for c in chars:
        n = len(samples[c]) if c in samples else 0
        print(f"  {c!r}: {n} campioni nuovi" + ("" if n else " (da template esistente)"))
    print(f"scritto {out}")


if __name__ == "__main__":
    main()
