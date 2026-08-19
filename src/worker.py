"""Unita' di lavoro per l'elaborazione parallela.

Sta in un modulo a se' perche' le funzioni passate a ProcessPoolExecutor
devono essere importabili (picklabili) dai processi figli.
"""
from pipeline import process_sheet


def process_one(args):
    """Elabora un foglio. Ritorna (path, righe, note, errore) senza propagare
    l'eccezione: un foglio illeggibile non deve fermare il lotto.

    `note` elenca i recuperi fatti in modalita' permissiva (griglia trovata con
    parametri diversi, card saltate): sono le cose da ricontrollare a mano.
    """
    image_path, dpi, drop_size, relaxed = args
    try:
        rows, notes = process_sheet(image_path, dpi=dpi, drop_size=drop_size,
                                    relaxed=relaxed)
        return image_path, rows, notes, None
    except Exception as e:
        # il tipo dell'eccezione dice dove si e' rotto: senza, "trovate 4" e
        # "nessuna regione non bianca" sembrano lo stesso genere di problema
        return image_path, [], [], f"{type(e).__name__}: {e}"
