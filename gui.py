#!/usr/bin/env python3
"""GUI: seleziona uno o piu' JPG di fogli A4, elabora, esporta un file Excel
nella cartella scelta dall'utente.
"""
import multiprocessing
import os
import queue
import subprocess
import sys
import threading
import tkinter.font as tkfont
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from tkinter import (
    Tk, StringVar, BooleanVar, filedialog, messagebox, ttk,
    END, EXTENDED, BOTH, LEFT, RIGHT, X, Y, N, S, W, E, VERTICAL,
)
from tkinter.scrolledtext import ScrolledText

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # senza tkinterdnd2 la GUI funziona, solo senza drag & drop
    DND_FILES = None
    TkinterDnD = None

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pipeline import find_duplicates, format_duplicates, write_xlsx  # noqa: E402
from worker import process_one  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

PROVISIONAL_NOTE = (
    "Formule ricavate dal bytecode del plugin DepositScan. DROP SIZE e' il "
    "volume di applicazione (L/ha): metadato del trattamento, non misurato "
    "dall'immagine."
)

# Palette: un solo posto da toccare per cambiare l'aspetto.
BG = "#eef1f5"        # sfondo finestra
SURFACE = "#ffffff"   # pannelli e campi
BORDER = "#d5dae2"
TEXT = "#1f2430"
MUTED = "#6b7280"
ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"
WARN = "#8a5a00"
ROW_ALT = "#f7f9fc"   # righe alternate della lista
BTN = "#f1f4f9"       # superficie dei pulsanti neutri

PAD = 12              # passo di spaziatura, usato ovunque


class App:
    def __init__(self, root):
        self.root = root
        root.title("DepositScan replica - esportazione Excel")
        root.geometry("1000x800")
        root.minsize(880, 700)
        root.configure(background=BG)

        self.image_paths = []
        self.tree_items = {}  # id riga Treeview -> percorso
        self.out_dir = StringVar(value=str(Path.home()))
        self.out_name = StringVar(value="output.xlsx")
        self.drop_size = StringVar(value="200")
        self.force = BooleanVar(value=False)
        self.status = StringVar(value="Pronto.")
        self.count_label = StringVar(value="Nessuna immagine in lista")
        self.log_queue = queue.Queue()
        self.last_output = None
        self.running = False

        self._init_style()
        self._build_layout()
        self._refresh_placeholder()
        self._poll_log_queue()

    # ------------------------------------------------------------------ stile

    def _init_style(self):
        """Tema 'clam' ricolorato: e' l'unico tema ttk che lascia ridefinire i
        colori dei widget anche su Windows, cosi' l'aspetto e' identico
        ovunque invece di seguire il tema di sistema."""
        style = ttk.Style(self.root)
        style.theme_use("clam")

        family = "Segoe UI" if sys.platform.startswith("win") else "DejaVu Sans"
        if family not in tkfont.families():
            family = tkfont.nametofont("TkDefaultFont").cget("family")
        self.font = (family, 10)
        self.font_bold = (family, 10, "bold")
        self.font_title = (family, 13, "bold")
        self.font_small = (family, 9)
        mono = "Consolas" if sys.platform.startswith("win") else "DejaVu Sans Mono"
        self.font_mono = (mono if mono in tkfont.families() else "TkFixedFont", 9)

        style.configure(".", background=BG, foreground=TEXT, font=self.font)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE, relief="solid",
                        borderwidth=1, bordercolor=BORDER)
        # contenitori DENTRO una card: stesso sfondo, nessun bordo. Riusare
        # Card.TFrame qui disegnerebbe un riquadro attorno a ogni gruppo.
        style.configure("CardBody.TFrame", background=SURFACE, borderwidth=0,
                        relief="flat")
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Card.TLabel", background=SURFACE, foreground=TEXT)
        style.configure("Title.TLabel", background=SURFACE, foreground=TEXT,
                        font=self.font_title)
        style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED,
                        font=self.font_small)
        style.configure("Warn.TLabel", background=BG, foreground=WARN,
                        font=self.font_small)
        style.configure("Status.TLabel", background=BG, foreground=MUTED)

        style.configure("TButton", background=BTN, foreground=TEXT,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        borderwidth=1, focusthickness=0, padding=(14, 7),
                        relief="solid")
        style.map("TButton",
                  background=[("pressed", "#dde3ec"), ("active", "#e8edf5"),
                              ("disabled", "#f4f6f9")],
                  foreground=[("disabled", "#a3aab6")],
                  bordercolor=[("active", ACCENT), ("disabled", "#e7eaf0")],
                  lightcolor=[("active", ACCENT), ("disabled", "#e7eaf0")],
                  darkcolor=[("active", ACCENT), ("disabled", "#e7eaf0")])

        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                        bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)
        style.map("Accent.TButton",
                  background=[("pressed", ACCENT_DARK), ("active", ACCENT_DARK),
                              ("disabled", "#a9bdf0")],
                  bordercolor=[("active", ACCENT_DARK), ("disabled", "#a9bdf0")],
                  lightcolor=[("active", ACCENT_DARK), ("disabled", "#a9bdf0")],
                  darkcolor=[("active", ACCENT_DARK), ("disabled", "#a9bdf0")],
                  foreground=[("disabled", "#eef2ff")])

        style.configure("Card.TCheckbutton", background=SURFACE, foreground=TEXT,
                        focusthickness=0, indicatorcolor=SURFACE,
                        indicatorbackground=SURFACE, bordercolor=BORDER)
        style.map("Card.TCheckbutton",
                  background=[("active", SURFACE)],
                  indicatorcolor=[("selected", ACCENT)],
                  bordercolor=[("active", ACCENT)])

        style.configure("TEntry", fieldbackground=SURFACE, foreground=TEXT,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        insertcolor=TEXT, padding=6, relief="flat")
        style.map("TEntry", bordercolor=[("focus", ACCENT)],
                  lightcolor=[("focus", ACCENT)], darkcolor=[("focus", ACCENT)])

        style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                        foreground=TEXT, rowheight=26, borderwidth=0, relief="flat")
        style.configure("Treeview.Heading", background="#f0f3f8", foreground=MUTED,
                        font=self.font_small, relief="flat", padding=(8, 6))
        style.map("Treeview.Heading", background=[("active", "#e6ebf3")])
        style.map("Treeview", background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])

        style.configure("TProgressbar", background=ACCENT, troughcolor="#e3e8ef",
                        bordercolor="#e3e8ef", lightcolor=ACCENT, darkcolor=ACCENT,
                        thickness=6)
        style.configure("Vertical.TScrollbar", background="#cfd6e0",
                        troughcolor=BG, bordercolor=BG, arrowcolor=MUTED,
                        relief="flat")
        style.map("Vertical.TScrollbar", background=[("active", MUTED)])
        style.configure("TPanedwindow", background=BG)
        style.configure("Sash", sashthickness=8, gripcount=0)

    # ----------------------------------------------------------------- layout

    def _build_layout(self):
        # grid e non pack: solo la riga 0 si allarga, le altre restano alla loro
        # altezza naturale. Con pack il PanedWindow si prenderebbe tutto lo
        # spazio e taglierebbe fuori le righe sotto.
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        panes = ttk.PanedWindow(self.root, orient=VERTICAL)
        panes.grid(row=0, column=0, sticky=N + S + E + W, padx=PAD, pady=(PAD, 0))
        # i pannelli devono essere figli diretti del PanedWindow
        panes.add(self._build_input_card(panes), weight=3)
        panes.add(self._build_log_card(panes), weight=2)

        self._build_options(row=1)
        self._build_actions(row=3)

    def _build_input_card(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=PAD)

        head = ttk.Frame(card, style="CardBody.TFrame")
        head.pack(fill=X)
        ttk.Label(head, text="Immagini da elaborare", style="Title.TLabel").pack(side=LEFT)
        ttk.Label(head, textvariable=self.count_label, style="Muted.TLabel").pack(side=RIGHT)

        bar = ttk.Frame(card, style="CardBody.TFrame")
        bar.pack(fill=X, pady=(PAD, 8))
        ttk.Button(bar, text="Aggiungi immagini...", command=self.add_images).pack(side=LEFT)
        ttk.Button(bar, text="Aggiungi cartella...", command=self.add_folder).pack(side=LEFT, padx=6)
        ttk.Button(bar, text="Svuota lista", command=self.clear_images).pack(side=RIGHT)
        ttk.Button(bar, text="Rimuovi selezionate", command=self.remove_selected).pack(side=RIGHT, padx=6)

        wrap = ttk.Frame(card, style="Card.TFrame")
        wrap.pack(fill=BOTH, expand=True)
        # EXTENDED: consente selezione multipla per la rimozione
        self.tree = ttk.Treeview(wrap, columns=("file", "folder"), show="headings",
                                 selectmode=EXTENDED)
        self.tree.heading("file", text="FILE", anchor=W)
        self.tree.heading("folder", text="CARTELLA", anchor=W)
        self.tree.column("file", width=280, anchor=W, stretch=False)
        self.tree.column("folder", width=420, anchor=W)
        self.tree.tag_configure("odd", background=ROW_ALT)
        self.tree.tag_configure("hint", foreground=MUTED)
        scroll = ttk.Scrollbar(wrap, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=RIGHT, fill=Y)
        self.tree.pack(fill=BOTH, expand=True)
        self.tree.bind("<Delete>", lambda _e: self.remove_selected())
        self._enable_drag_and_drop(self.tree)
        return card

    def _build_options(self, row):
        card = ttk.Frame(self.root, style="Card.TFrame", padding=PAD)
        card.grid(row=row, column=0, sticky=E + W, padx=PAD, pady=(PAD, 0))
        ttk.Label(card, text="Output", style="Title.TLabel").grid(
            row=0, column=0, columnspan=6, sticky=W, pady=(0, PAD))

        def field(row, col, text, var, width, span=1):
            ttk.Label(card, text=text, style="Card.TLabel").grid(
                row=row, column=col, sticky=W, padx=(16 if col else 0, 8), pady=4)
            ttk.Entry(card, textvariable=var, width=width, font=self.font).grid(
                row=row, column=col + 1, columnspan=span, sticky=W + E, pady=4)

        # due righe invece di quattro: la finestra resta bassa e le voci
        # correlate stanno vicine
        field(1, 0, "Cartella output:", self.out_dir, 52, span=4)
        ttk.Button(card, text="Scegli...", command=self.choose_out_dir).grid(
            row=1, column=5, sticky=W, padx=(8, 0), pady=4)
        field(2, 0, "Nome file Excel:", self.out_name, 24)
        field(2, 2, "DROP SIZE (L/ha):", self.drop_size, 8)
        card.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            card, variable=self.force, style="Card.TCheckbutton",
            text="Elabora comunque i fogli problematici (griglia cercata con "
                 "parametri permissivi; se una card e' illeggibile salva le altre)",
        ).grid(row=3, column=0, columnspan=6, sticky=W, pady=(PAD, 0))

        note = ttk.Label(self.root, text=PROVISIONAL_NOTE, style="Warn.TLabel",
                         wraplength=900, justify=LEFT)
        note.grid(row=row + 1, column=0, sticky=W + E, padx=PAD, pady=(8, 0))
        # il testo va a capo sulla larghezza reale, non su una stima fissa
        note.bind("<Configure>",
                  lambda e: note.configure(wraplength=max(300, e.width - 8)))

    def _build_actions(self, row):
        bar = ttk.Frame(self.root)
        bar.grid(row=row, column=0, sticky=E + W, padx=PAD, pady=(8, 0))
        self.run_button = ttk.Button(bar, text="Elabora ed esporta Excel",
                                     style="Accent.TButton", command=self.run_pipeline)
        self.run_button.pack(side=LEFT)
        self.open_button = ttk.Button(bar, text="Apri cartella output",
                                      command=self.open_out_dir, state="disabled")
        self.open_button.pack(side=LEFT, padx=8)

        self.progress = ttk.Progressbar(bar, mode="determinate", style="TProgressbar")
        self.progress.pack(side=LEFT, fill=X, expand=True, padx=(PAD, 0))

        status = ttk.Frame(self.root)
        status.grid(row=row + 1, column=0, sticky=E + W, padx=PAD, pady=(6, PAD))
        ttk.Label(status, textvariable=self.status, style="Status.TLabel").pack(side=LEFT)

    def _build_log_card(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=PAD)
        head = ttk.Frame(card, style="CardBody.TFrame")
        head.pack(fill=X, pady=(0, 8))
        ttk.Label(head, text="Log", style="Title.TLabel").pack(side=LEFT)
        ttk.Button(head, text="Svuota log", command=self.clear_log).pack(side=RIGHT)
        self.log_text = ScrolledText(
            card, height=10, state="disabled", font=self.font_mono,
            background=SURFACE, foreground=TEXT, insertbackground=TEXT,
            relief="flat", borderwidth=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER, padx=8, pady=6,
        )
        self.log_text.pack(fill=BOTH, expand=True)
        return card

    # ------------------------------------------------------------ lista input

    def _enable_drag_and_drop(self, widget):
        """Registra il widget come bersaglio di drag & drop, se tkinterdnd2 c'e'."""
        if TkinterDnD is None or not hasattr(self.root, "drop_target_register"):
            return
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", self._on_drop)
        self.dnd_ready = True

    def _on_drop(self, event):
        # event.data e' una lista in formato Tcl: i path con spazi sono fra graffe
        dropped = self.root.tk.splitlist(event.data)
        found = []
        for item in dropped:
            p = Path(item)
            if p.is_dir():
                found.extend(self._scan_folder(p))
            elif p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES:
                found.append(str(p))
        if not found:
            self.status.set("Nessuna immagine riconosciuta fra gli elementi trascinati.")
            return
        self._add_paths(found)

    @staticmethod
    def _scan_folder(folder):
        return sorted(
            str(p) for p in Path(folder).rglob("*")
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
        )

    def _refresh_placeholder(self):
        """Riga segnaposto quando la lista e' vuota: spiega il drag & drop."""
        if self.image_paths:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        hint = ("Trascina qui i file o le cartelle"
                if getattr(self, "dnd_ready", False)
                else "Usa i pulsanti qui sopra per aggiungere le immagini")
        self.tree.insert("", END, iid="__hint__", values=(hint, ""), tags=("hint",))

    def _redraw_rows(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_items.clear()
        for i, p in enumerate(self.image_paths):
            path = Path(p)
            iid = self.tree.insert("", END, values=(path.name, str(path.parent)),
                                   tags=("odd",) if i % 2 else ())
            self.tree_items[iid] = p
        self._update_counter()
        self._refresh_placeholder()

    def _update_counter(self):
        n = len(self.image_paths)
        self.count_label.set("Nessuna immagine in lista" if not n
                             else f"{n} immagine in lista" if n == 1
                             else f"{n} immagini in lista")

    def _add_paths(self, paths):
        added = 0
        for p in paths:
            if p not in self.image_paths:
                self.image_paths.append(p)
                added += 1
        self._redraw_rows()
        self.status.set(f"{added} aggiunte." if added else "Gia' presenti in lista.")
        return added

    def add_images(self):
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_SUFFIXES))
        paths = filedialog.askopenfilenames(
            title="Seleziona le immagini dei fogli A4",
            filetypes=[("Immagini", exts), ("Tutti i file", "*.*")],
        )
        if paths:
            self._add_paths(paths)

    def add_folder(self):
        d = filedialog.askdirectory(title="Scegli la cartella con le immagini")
        if not d:
            return
        self._add_paths(self._scan_folder(d))

    def remove_selected(self):
        removed = [self.tree_items[i] for i in self.tree.selection() if i in self.tree_items]
        if not removed:
            return
        self.image_paths = [p for p in self.image_paths if p not in set(removed)]
        self._redraw_rows()
        self.status.set(f"{len(removed)} rimosse.")

    def clear_images(self):
        self.image_paths.clear()
        self._redraw_rows()
        self.status.set("Lista svuotata.")

    # ---------------------------------------------------------------- output

    def choose_out_dir(self):
        d = filedialog.askdirectory(title="Scegli la cartella di output")
        if d:
            self.out_dir.set(d)

    def open_out_dir(self):
        d = Path(self.out_dir.get()).expanduser()
        try:
            d = d.resolve()
        except OSError:
            pass
        if not d.is_dir():
            messagebox.showerror("Cartella non valida", f"'{d}' non esiste.")
            return
        try:
            if sys.platform.startswith("win"):
                # explorer.exe con un percorso che non sa interpretare (barre
                # unix, path relativo) non segnala l'errore: apre Documenti.
                # Serve un percorso assoluto con separatori Windows.
                target = os.path.normpath(str(d))
                if self.last_output and Path(self.last_output).parent == d:
                    # /select, evidenzia il file appena scritto
                    subprocess.Popen(
                        ["explorer", f"/select,{os.path.normpath(str(self.last_output))}"])
                else:
                    os.startfile(target)  # noqa: S606  (solo su Windows)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(d)])
            else:
                # su WSL apre Esplora risorse di Windows, altrove xdg-open
                opener = "wslview" if Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists() else "xdg-open"
                subprocess.Popen([opener, str(d)])
        except Exception as e:
            messagebox.showwarning("Impossibile aprire", f"Apri manualmente:\n{d}\n\n({e})")

    def _log(self, msg):
        self.log_queue.put(msg)

    def clear_log(self):
        # svuotare anche la coda: i messaggi gia' in attesa ricomparirebbero
        # nel widget al giro successivo di _poll_log_queue
        while True:
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                break
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", END)
        self.log_text.configure(state="disabled")

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

    # -------------------------------------------------------------- pipeline

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
        out_name = self.out_name.get().strip() or "output.xlsx"
        if not out_name.lower().endswith(".xlsx"):
            out_name += ".xlsx"
        out_path = out_dir / out_name
        if out_path.exists() and not messagebox.askyesno(
            "File esistente", f"{out_path.name} esiste gia'. Sovrascrivere?"
        ):
            return

        try:
            drop_size = int(self.drop_size.get().strip())
        except ValueError:
            messagebox.showerror("Valore non valido", "DROP SIZE deve essere un numero (L/ha).")
            return
        self.running = True
        self.clear_log()
        self.run_button.config(state="disabled")
        self.progress.configure(maximum=len(self.image_paths), value=0)
        threading.Thread(
            target=self._process_worker,
            args=(list(self.image_paths), out_path, drop_size, self.force.get()),
            daemon=True
        ).start()

    def _process_worker(self, image_paths, out_path, drop_size, force):
        results, failed = {}, []
        bad_labels = bad_quality = 0
        total = len(image_paths)
        try:
            jobs = max(1, min(multiprocessing.cpu_count() or 1, total))
            tasks = [(p, 600.0, drop_size, force) for p in image_paths]
            done = 0

            def handle(path, rows, notes, err):
                nonlocal done, bad_labels, bad_quality
                done += 1
                self.root.after(0, self.status.set, f"Elaborazione {done}/{total}...")
                self.root.after(0, self.progress.configure, {"value": done})
                if err:
                    failed.append((path, err))
                    # percorso completo e motivo su righe separate: e' quello
                    # che serve per andare a riprendere il foglio a mano
                    self._log(f"[{done}/{total}] SALTATO  {path}")
                    self._log(f"          motivo: {err}")
                    return
                results[path] = rows
                notes = list(notes)
                for r in rows:
                    if not r["label_ok"]:
                        notes.append(f"card {r['card_index']} etichetta '{r['label_raw_text']}'")
                        bad_labels += 1
                    if str(r["quality_flag"]).startswith("SFONDO"):
                        notes.append(f"card {r['card_index']} scansione degradata")
                        bad_quality += 1
                self._log(f"[{done}/{total}] {Path(path).name}")
                for n in notes:
                    self._log(f"          ! {n}")

            if jobs == 1:
                for t in tasks:
                    handle(*process_one(t))
            else:
                with ProcessPoolExecutor(max_workers=jobs) as pool:
                    futures = [pool.submit(process_one, t) for t in tasks]
                    for fut in as_completed(futures):
                        handle(*fut.result())

            # ordine di output stabile: come in lista, non come finiscono
            all_rows = [r for p in image_paths for r in results.get(p, [])]
            if not all_rows:
                raise RuntimeError("Nessuna card elaborata: controlla i file di input.")

            write_xlsx(all_rows, str(out_path))
            self.last_output = out_path

            dups = find_duplicates(all_rows)

            summary = [f"Scritte {len(all_rows)} righe in {out_path}"]
            if dups:
                summary.append(f"{len(dups)} etichette duplicate (elenco nel log)")
            if bad_labels:
                summary.append(f"{bad_labels} etichette non riconosciute (da verificare a mano)")
            if bad_quality:
                summary.append(f"{bad_quality} card con scansione degradata")
            if failed:
                summary.append(f"{len(failed)} fogli saltati (elenco nel log)")
            self._log("Fatto. " + " | ".join(summary))
            if dups:
                # stessa etichetta due volte nello stesso output: una delle due
                # card e' stata scansionata o etichettata male, va controllata
                self._log(f"\n{len(dups)} etichette duplicate nello stesso output:")
                for line in format_duplicates(dups):
                    self._log(line)
            if failed:
                # elenco finale: il log scorre durante l'elaborazione, qui i
                # fogli da recuperare restano tutti insieme in fondo
                self._log(f"\n{len(failed)} fogli NON elaborati, da recuperare a mano:")
                for p, e in failed:
                    self._log(f"  {p}")
                    self._log(f"      motivo: {e}")
                if not force:
                    self._log("  Suggerimento: riprova con "
                              "'Elabora comunque i fogli problematici' attivo.")
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
    root = TkinterDnD.Tk() if TkinterDnD is not None else Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # necessario per l'eseguibile Windows
    main()
