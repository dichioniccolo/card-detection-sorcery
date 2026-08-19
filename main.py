#!/usr/bin/env python3
"""CLI: da uno o piu' JPG di fogli A4 (4 sticky card ciascuno) genera un CSV
con le metriche per card.

Uso:
    python main.py assets/*.jpg -o out.csv
    python main.py cartella/*.jpg -o out.csv -j 8
"""
import argparse
import multiprocessing
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline import write_csv  # noqa: E402
from worker import process_one  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", help="JPG dei fogli A4 da processare")
    parser.add_argument("-o", "--output", default="output.csv", help="file CSV di output")
    parser.add_argument("--dpi", type=float, default=600.0, help="DPI di scansione (default 600)")
    parser.add_argument("--drop-size", type=int, default=200,
                        help="volume di applicazione in L/ha, colonna DROP SIZE (default 200)")
    parser.add_argument("-j", "--jobs", type=int, default=0,
                        help="processi paralleli (default: numero di CPU)")
    parser.add_argument("--force", action="store_true",
                        help="elabora comunque i fogli problematici: cerca la griglia con "
                             "parametri permissivi e, se una card e' illeggibile, salva "
                             "lo stesso le altre tre")
    args = parser.parse_args()

    jobs = args.jobs if args.jobs > 0 else (multiprocessing.cpu_count() or 1)
    jobs = max(1, min(jobs, len(args.images)))

    tasks = [(p, args.dpi, args.drop_size, args.force) for p in args.images]
    total = len(tasks)
    results = {}
    failed = []

    print(f"{total} immagini, {jobs} processi paralleli", file=sys.stderr)

    if jobs == 1:
        done = 0
        for t in tasks:
            path, rows, notes, err = process_one(t)
            done += 1
            _report(path, rows, notes, err, done, total, results, failed)
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            futures = {pool.submit(process_one, t): t[0] for t in tasks}
            done = 0
            for fut in as_completed(futures):
                path, rows, notes, err = fut.result()
                done += 1
                _report(path, rows, notes, err, done, total, results, failed)

    # ordine di output stabile: come sulla riga di comando, non come finiscono
    all_rows = [r for p in args.images for r in results.get(p, [])]
    write_csv(all_rows, args.output)

    print(f"Scritte {len(all_rows)} righe in {args.output}", file=sys.stderr)
    if failed:
        print(f"\n{len(failed)} fogli NON elaborati, da recuperare a mano:", file=sys.stderr)
        for p, e in failed:
            print(f"  {p}\n      motivo: {e}", file=sys.stderr)
        if not args.force:
            print("  (riprova con --force per elaborarli comunque)", file=sys.stderr)


def _report(path, rows, notes, err, done, total, results, failed):
    if err:
        failed.append((path, err))
        print(f"[{done}/{total}] SALTATO  {path}\n      motivo: {err}", file=sys.stderr)
        return
    results[path] = rows
    notes = list(notes)
    for r in rows:
        if not r["label_ok"]:
            notes.append(f"card {r['card_index']} etichetta '{r['label_raw_text']}'")
        if str(r["quality_flag"]).startswith("SFONDO"):
            notes.append(f"card {r['card_index']} scansione degradata")
    print(f"[{done}/{total}] {path}", file=sys.stderr)
    for n in notes:
        print(f"      ! {n}", file=sys.stderr)


if __name__ == "__main__":
    multiprocessing.freeze_support()  # necessario per l'eseguibile Windows
    main()
