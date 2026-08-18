#!/usr/bin/env python3
"""CLI: da uno o piu' JPG di fogli A4 (4 sticky card ciascuno) genera un CSV
con le metriche per card.

Uso:
    python main.py assets/PROVA_A_0027.jpg assets/PROVA_B_0007.jpg -o out.csv
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline import process_sheet, write_csv  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", help="JPG dei fogli A4 da processare")
    parser.add_argument("-o", "--output", default="output.csv", help="file CSV di output")
    parser.add_argument("--dpi", type=float, default=600.0, help="DPI di scansione (default 600)")
    parser.add_argument("--drop-size", type=int, default=200,
                        help="volume di applicazione in L/ha, colonna DROP SIZE (default 200)")
    args = parser.parse_args()

    all_rows = []
    for image_path in args.images:
        print(f"Elaborazione {image_path} ...", file=sys.stderr)
        rows = process_sheet(image_path, dpi=args.dpi, drop_size=args.drop_size)
        for r in rows:
            status = "OK" if r["label_ok"] else "ETICHETTA NON RICONOSCIUTA"
            if r["quality_flag"] != "OK":
                status += " / SCANSIONE DEGRADATA"
            print(f"  card {r['card_index']}: {status} -> {r['label_raw_text']!r}", file=sys.stderr)
        all_rows.extend(rows)

    write_csv(all_rows, args.output)
    print(f"Scritte {len(all_rows)} righe in {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
