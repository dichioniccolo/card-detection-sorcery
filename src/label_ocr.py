"""Lettura dell'etichetta associata a ciascuna card.

Le etichette sono stampate con un font monospace fisso e usano un alfabeto
ristretto (`H P R M V U D W A B C` piu' le cifre). Il riconoscimento avviene
per confronto con template costruiti dai fogli di riferimento
(`tools/build_label_templates.py`), non con un OCR generico: e' piu'
affidabile su questo font e soprattutto non richiede dipendenze esterne,
cosi' l'applicazione resta distribuibile come singolo eseguibile.

L'OCR e' applicato SOLO al ritaglio dell'etichetta, mai all'intero foglio.
"""
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from label_glyphs import segment_glyphs, normalize_glyph

_LABEL_RE = re.compile(
    r"H(?P<height>\d+)P(?P<plant>\d+)R(?P<replica>\d+)"
    r"(?P<side>[MV])(?P<direction>UP|DW)(?P<test>[A-D])"
)

_TEMPLATES = None
_CHARS = None


def _templates_path() -> Path:
    # in un eseguibile PyInstaller i dati stanno nella cartella temporanea
    # di estrazione (sys._MEIPASS), non accanto al sorgente
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "label_templates.npz"
    return Path(__file__).with_name("label_templates.npz")


def _load_templates():
    global _TEMPLATES, _CHARS
    if _TEMPLATES is None:
        data = np.load(_templates_path())
        _CHARS = [str(c) for c in data["chars"]]
        _TEMPLATES = data["templates"]
    return _CHARS, _TEMPLATES


DIGITS = "0123456789"

# L'etichetta ha una struttura fissa: H<cifra> P<cifra> R<cifra> <M|V>
# <UP|DW> <A-D>. Vincolare ogni posizione ai soli caratteri ammessi elimina
# le confusioni fra glifi simili (es. P letto come A).
_POSITION_ALPHABET = ["H", DIGITS, "P", DIGITS, "R", DIGITS, "MV", None, None, "ABCD"]


def _distances(glyph: np.ndarray):
    chars, templates = _load_templates()
    v = normalize_glyph(glyph)
    dist = np.sqrt(((templates - v) ** 2).sum(axis=(1, 2)))
    return {c: float(dist[i]) for i, c in enumerate(chars)}


def _pick(dists: dict, allowed: str):
    """Carattere piu' vicino fra quelli ammessi, con il margine sul secondo."""
    cand = sorted(((dists[c], c) for c in allowed if c in dists))
    if not cand:
        return "?", float("inf"), 0.0
    best_d, best_c = cand[0]
    margin = cand[1][0] - best_d if len(cand) > 1 else float("inf")
    return best_c, best_d, margin


def read_label(image: Image.Image, label_box: tuple) -> dict:
    gray = np.array(image.crop(label_box).convert("L"))
    glyphs = segment_glyphs(gray)

    if len(glyphs) != len(_POSITION_ALPHABET):
        text = "".join(_pick(_distances(g), "".join(sorted(_load_templates()[0])))[0]
                       for g in glyphs)
        return {"ok": False, "raw_text": text, "compact_text": text}

    dists = [_distances(g) for g in glyphs]

    chars, worst_margin = [], float("inf")
    for i, allowed in enumerate(_POSITION_ALPHABET):
        if allowed is None:
            continue
        ch, _d, margin = _pick(dists[i], allowed)
        chars.append((i, ch))
        worst_margin = min(worst_margin, margin)

    # posizioni 7-8: la direzione e' "UP" oppure "DW", si sceglie la coppia
    # con il costo complessivo minore invece dei due caratteri separatamente
    up = dists[7].get("U", float("inf")) + dists[8].get("P", float("inf"))
    dw = dists[7].get("D", float("inf")) + dists[8].get("W", float("inf"))
    direction = "UP" if up <= dw else "DW"
    worst_margin = min(worst_margin, abs(up - dw))

    out = dict(chars)
    text = (out[0] + out[1] + out[2] + out[3] + out[4] + out[5] + out[6]
            + direction + out[9])

    m = _LABEL_RE.fullmatch(text)
    if not m:
        return {"ok": False, "raw_text": text, "compact_text": text}

    d = m.groupdict()
    return {
        "ok": True,
        "raw_text": text,
        "height": int(d["height"]),
        "plant": int(d["plant"]),
        "replica": int(d["replica"]),
        "side": d["side"],
        "direction": d["direction"],
        "test": d["test"],
        "match_margin": worst_margin,
    }
