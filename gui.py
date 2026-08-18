#!/usr/bin/env python3
"""GUI: seleziona uno o piu' JPG di fogli A4, elabora, esporta CSV nella
cartella scelta dall'utente.
"""
import queue
import sys
import threading
from pathlib import Path
from tkinter import (
    Tk, Frame, Listbox, Scrollbar, Button, Label, Entry, StringVar,
    filedialog, messagebox, END, SINGLE, BOTH, LEFT, RIGHT, X, Y, W,
)
from tkinter.scrolledtext import ScrolledText

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline import process_sheet, write_csv  # noqa: E402


class App:
    def __init__(self, root):
        self.root = root
        root.title("DepositScan replica - esportazione CSV")
        root.geometry("720x520")

        self.image_paths = []
        self.out_dir = StringVar(value=str(Path.home()))
        self.out_name = StringVar(value="output.csv")
        self.log_queue = queue.Queue()

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
        self.listbox = Listbox(list_frame, selectmode=SINGLE, yscrollcommand=scrollbar.set)
        self.listbox.pack(fill=BOTH, expand=True)
        scrollbar.config(command=self.listbox.yview)

        out_frame = Frame(self.root, padx=10, pady=8)
        out_frame.pack(fill=X)

        Label(out_frame, text="Cartella output:").grid(row=0, column=0, sticky=W)
        Entry(out_frame, textvariable=self.out_dir, width=55).grid(row=0, column=1, sticky=W, padx=6)
        Button(out_frame, text="Scegli...", command=self.choose_out_dir).grid(row=0, column=2)

        Label(out_frame, text="Nome file CSV:").grid(row=1, column=0, sticky=W, pady=(6, 0))
        Entry(out_frame, textvariable=self.out_name, width=30).grid(row=1, column=1, sticky=W, padx=6, pady=(6, 0))

        action_frame = Frame(self.root, padx=10, pady=4)
        action_frame.pack(fill=X)
        self.run_button = Button(action_frame, text="Elabora ed esporta CSV", command=self.run_pipeline)
        self.run_button.pack(side=LEFT)

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
        for p in paths:
            if p not in self.image_paths:
                self.image_paths.append(p)
                self.listbox.insert(END, p)

    def remove_selected(self):
        sel = self.listbox.curselection()
        for idx in reversed(sel):
            self.listbox.delete(idx)
            del self.image_paths[idx]

    def clear_images(self):
        self.listbox.delete(0, END)
        self.image_paths.clear()

    def choose_out_dir(self):
        d = filedialog.askdirectory(title="Scegli la cartella di output")
        if d:
            self.out_dir.set(d)

    def _log(self, msg: str):
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

        self.run_button.config(state="disabled")
        thread = threading.Thread(target=self._process_worker, args=(list(self.image_paths), out_path), daemon=True)
        thread.start()

    def _process_worker(self, image_paths, out_path):
        all_rows = []
        try:
            for image_path in image_paths:
                self._log(f"Elaborazione {image_path} ...")
                rows = process_sheet(image_path)
                for r in rows:
                    status = "OK" if r["label_ok"] else "ETICHETTA NON RICONOSCIUTA"
                    self._log(f"  card {r['card_index']}: {status} -> {r['label_raw_text']!r}")
                all_rows.extend(rows)

            write_csv(all_rows, str(out_path))
            self._log(f"Fatto: {len(all_rows)} righe scritte in {out_path}")
            self.root.after(0, lambda: messagebox.showinfo("Completato", f"CSV esportato in:\n{out_path}"))
        except Exception as e:
            self._log(f"ERRORE: {e}")
            self.root.after(0, lambda: messagebox.showerror("Errore", str(e)))
        finally:
            self.root.after(0, lambda: self.run_button.config(state="normal"))


def main():
    root = Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
