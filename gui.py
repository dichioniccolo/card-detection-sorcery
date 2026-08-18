#!/usr/bin/env python3
"""GUI: seleziona uno o piu' JPG di fogli A4, elabora, esporta CSV nella
cartella scelta dall'utente.
"""
import queue
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import (
    Tk, Frame, Listbox, Scrollbar, Button, Label, Entry, StringVar,
    filedialog, messagebox, END, EXTENDED, BOTH, LEFT, RIGHT, X, Y, W,
)
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline import process_sheet, write_csv  # noqa: E402

PROVISIONAL_NOTE = (
    "Coverage, Image area, Total deposit e Deposits/cm2 sono validati sui dati "
    "DepositScan.  DV01/DV05/DV09 e uL/cm2 sono PROVVISORI."
)


class App:
    def __init__(self, root):
        self.root = root
        root.title("DepositScan replica - esportazione CSV")
        root.geometry("820x620")
        root.minsize(700, 520)

        self.image_paths = []
        self.out_dir = StringVar(value=str(Path.home()))
        self.out_name = StringVar(value="output.csv")
        self.status = StringVar(value="Pronto.")
        self.log_queue = queue.Queue()
        self.last_output = None
        self.running = False

        self._build_layout()
        self._poll_log_queue()

    def _build_layout(self):
        top = Frame(self.root, padx=10, pady=10)
        top.pack(fill=X)
        Button(top, text="Aggiungi immagini...", command=self.add_images).pack(side=LEFT)
        Button(top, text="Rimuovi selezionate", command=self.remove_selected).pack(side=LEFT, padx=6)
        Button(top, text="Svuota lista", command=self.clear_images).pack(side=LEFT)

        list_frame = Frame(self.root, padx=10)
        list_frame.pack(fill=BOTH, expand=True)
        scrollbar = Scrollbar(list_frame)
        scrollbar.pack(side=RIGHT, fill=Y)
        # EXTENDED: consente selezione multipla per la rimozione
        self.listbox = Listbox(list_frame, selectmode=EXTENDED, yscrollcommand=scrollbar.set)
        self.listbox.pack(fill=BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        out_frame = Frame(self.root, padx=10, pady=8)
        out_frame.pack(fill=X)
        Label(out_frame, text="Cartella output:").grid(row=0, column=0, sticky=W)
        Entry(out_frame, textvariable=self.out_dir, width=58).grid(row=0, column=1, sticky=W, padx=6)
        Button(out_frame, text="Scegli...", command=self.choose_out_dir).grid(row=0, column=2)
        Label(out_frame, text="Nome file CSV:").grid(row=1, column=0, sticky=W, pady=(6, 0))
        Entry(out_frame, textvariable=self.out_name, width=30).grid(row=1, column=1, sticky=W, padx=6, pady=(6, 0))

        action = Frame(self.root, padx=10, pady=4)
        action.pack(fill=X)
        self.run_button = Button(action, text="Elabora ed esporta CSV", command=self.run_pipeline)
        self.run_button.pack(side=LEFT)
        self.open_button = Button(action, text="Apri cartella output", command=self.open_out_dir, state="disabled")
        self.open_button.pack(side=LEFT, padx=6)
        Label(action, textvariable=self.status).pack(side=LEFT, padx=12)

        Label(self.root, text=PROVISIONAL_NOTE, wraplength=790, justify=LEFT,
              fg="#8a5a00").pack(fill=X, padx=10, pady=(2, 0), anchor=W)

        log_frame = Frame(self.root, padx=10, pady=8)
        log_frame.pack(fill=BOTH, expand=True)
        Label(log_frame, text="Log:").pack(anchor=W)
        self.log_text = ScrolledText(log_frame, height=12, state="disabled")
        self.log_text.pack(fill=BOTH, expand=True)

    def add_images(self):
        paths = filedialog.askopenfilenames(
            title="Seleziona i JPG dei fogli A4",
            filetypes=[("Immagini JPG", "*.jpg *.jpeg *.JPG *.JPEG"), ("Tutti i file", "*.*")],
        )
        added = 0
        for p in paths:
            if p not in self.image_paths:
                self.image_paths.append(p)
                self.listbox.insert(END, p)
                added += 1
        if added:
            self.status.set(f"{len(self.image_paths)} immagini in lista.")

    def remove_selected(self):
        for idx in reversed(self.listbox.curselection()):
            self.listbox.delete(idx)
            del self.image_paths[idx]
        self.status.set(f"{len(self.image_paths)} immagini in lista.")

    def clear_images(self):
        self.listbox.delete(0, END)
        self.image_paths.clear()
        self.status.set("Lista svuotata.")

    def choose_out_dir(self):
        d = filedialog.askdirectory(title="Scegli la cartella di output")
        if d:
            self.out_dir.set(d)

    def open_out_dir(self):
        d = self.out_dir.get()
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", d])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                # su WSL apre Esplora risorse di Windows, altrove xdg-open
                opener = "wslview" if Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists() else "xdg-open"
                subprocess.Popen([opener, d])
        except Exception as e:
            messagebox.showwarning("Impossibile aprire", f"Apri manualmente:\n{d}\n\n({e})")

    def _log(self, msg):
        self.log_queue.put(msg)

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert(END, msg + "\n")
                self.log_text.see(END)
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_log_queue)

    def run_pipeline(self):
        if self.running:
            return
        if not self.image_paths:
            messagebox.showwarning("Nessuna immagine", "Aggiungi almeno un JPG prima di elaborare.")
            return
        out_dir = Path(self.out_dir.get())
        if not out_dir.is_dir():
            messagebox.showerror("Cartella non valida", f"'{out_dir}' non esiste.")
            return
        out_name = self.out_name.get().strip() or "output.csv"
        if not out_name.lower().endswith(".csv"):
            out_name += ".csv"
        out_path = out_dir / out_name
        if out_path.exists() and not messagebox.askyesno(
            "File esistente", f"{out_path.name} esiste gia'. Sovrascrivere?"
        ):
            return

        self.running = True
        self.run_button.config(state="disabled")
        threading.Thread(
            target=self._process_worker, args=(list(self.image_paths), out_path), daemon=True
        ).start()

    def _process_worker(self, image_paths, out_path):
        all_rows = []
        bad_labels = 0
        bad_quality = 0
        failed_sheets = []
        total = len(image_paths)
        try:
            for n, image_path in enumerate(image_paths, 1):
                self.root.after(0, self.status.set, f"Elaborazione {n}/{total}...")
                self._log(f"[{n}/{total}] {image_path}")
                try:
                    rows = process_sheet(image_path)
                except Exception as e:
                    # un foglio illeggibile non deve interrompere il lotto
                    failed_sheets.append(image_path)
                    self._log(f"    SALTATO - {e}")
                    continue
                for r in rows:
                    notes = []
                    if not r["label_ok"]:
                        notes.append(f"ETICHETTA NON LETTA ({r['label_raw_text']!r})")
                        bad_labels += 1
                    if r["quality_flag"] != "OK":
                        notes.append("SCANSIONE DEGRADATA: sfondo sotto soglia, "
                                     "Coverage inaffidabile")
                        bad_quality += 1
                    suffix = "  <-- " + "; ".join(notes) if notes else ""
                    self._log(f"    card {r['card_index']}: {r['label_raw_text']}{suffix}")
                all_rows.extend(rows)

            if not all_rows:
                raise RuntimeError("Nessuna card elaborata: controlla i file di input.")

            write_csv(all_rows, str(out_path))
            self.last_output = out_path

            summary = [f"Scritte {len(all_rows)} righe in {out_path}"]
            if bad_labels:
                summary.append(f"{bad_labels} etichette non riconosciute (da verificare a mano)")
            if bad_quality:
                summary.append(f"{bad_quality} card con scansione degradata")
            if failed_sheets:
                summary.append(f"{len(failed_sheets)} fogli saltati")
            self._log("Fatto. " + " | ".join(summary))
            self.root.after(0, self.status.set, f"Completato: {len(all_rows)} righe.")
            self.root.after(0, self.open_button.config, {"state": "normal"})
            self.root.after(0, lambda: messagebox.showinfo("Completato", "\n".join(summary)))
        except Exception as e:
            self._log(f"ERRORE: {e}")
            self.root.after(0, self.status.set, "Errore.")
            self.root.after(0, lambda: messagebox.showerror("Errore", str(e)))
        finally:
            self.running = False
            self.root.after(0, self.run_button.config, {"state": "normal"})


def main():
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
