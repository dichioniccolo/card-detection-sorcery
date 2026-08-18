"""Unita' di lavoro per l'elaborazione parallela.

Sta in un modulo a se' perche' le funzioni passate a ProcessPoolExecutor
devono essere importabili (picklabili) dai processi figli.
"""
from pipeline import process_sheet


def process_one(args):
    """Elabora un foglio. Ritorna (path, righe, errore) senza propagare
    l'eccezione: un foglio illeggibile non deve fermare il lotto."""
    image_path, dpi, drop_size = args
    try:
        return image_path, process_sheet(image_path, dpi=dpi, drop_size=drop_size), None
    except Exception as e:
        return image_path, [], str(e)
