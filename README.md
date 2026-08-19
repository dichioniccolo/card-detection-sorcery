# Replica indipendente di DepositScan

Da JPG di fogli A4 scansionati (4 sticky card ciascuno) produce un CSV con
metadati e metriche di deposito per ogni card.

## Uso

GUI:

```bash
venv/bin/python3 gui.py
```

Riga di comando (`-j` = processi paralleli, default: numero di CPU):

```bash
venv/bin/python3 main.py assets/*.jpg -o output.csv -j 8
```

Un foglio su cui la griglia non viene trovata, o con una card illeggibile,
viene saltato: il log ne stampa percorso completo e motivo, cosi' si sa cosa
recuperare a mano. Con `--force` (nella GUI: *Elabora comunque i fogli
problematici*) il foglio viene ripreso lo stesso:

- la griglia si cerca con un sweep di parametri piu' permissivi, e il log dice
  quali hanno funzionato;
- una card illeggibile non fa piu' perdere le altre tre: esce una riga senza
  metriche, con `quality_flag = CARD_NON_ELABORATA: <motivo>`.

Le righe recuperate cosi' vanno controllate a mano: la griglia trovata con
parametri diversi puo' ritagliare le card in modo leggermente diverso.

Nessuna dipendenza esterna oltre ai pacchetti in `requirements.txt`.

### Eseguibile Windows

Su Windows, con Python installato, `build_windows.bat` produce
`dist\DepositScanReplica.exe`: file singolo, avvia la GUI, condivisibile
com'e'.

## Pipeline

1. rilevamento della griglia prestampata (linee della tabella)
2. individuazione delle 4 card e delle 4 etichette
3. lettura dell'etichetta per confronto con template di caratteri, vincolata
   al formato `H# P# R# [M|V] [UP|DW] [A-D]`
4. conversione 8-bit come ImageJ: media non pesata `(R+G+B)/3`, arrotondata
5. soglia **inclusiva** a 127: deposito = pixel `<= 127`
6. componenti connesse (8-connettivita', nessun filtro dimensionale)
7. scarto delle particelle con diametro goccia `<= 50 µm`
8. metriche sul **bounding box** della card, a 600 DPI

## Stato di validazione

Riferimento: 24 card reali con risultati DepositScan noti. Le due card
degradate di `PROVA_A_0030` sono escluse dalle statistiche (vedi sotto).

| Metrica | Bias | MAE |
|---|---|---|
| DV01 | +0.04 % | 0.45 % |
| DV05 | +0.08 % | 0.21 % |
| DV09 | +0.08 % | 0.12 % |
| COVERAGE | +0.01 % | 1.70 % |
| IMAGE AREA | -0.08 % | 1.53 % |
| TOTAL DEPOSIT | +0.29 % | 0.29 % |
| DROP DENSITY | +0.42 % | 1.50 % |
| µL | -0.16 % | 1.81 % |

Lo scarto residuo viene dalla delimitazione della ROI rettangolare, che in
DepositScan e' tracciata a mano dall'operatore: e' l'unico passo non
deterministico della catena.

Parametri non documentati nel paper, ricavati dal bytecode del plugin
(`depositscan/plugins/Java program/`) e confermati dai dati:

- **Conversione 8-bit**: verificata direttamente contro gli screenshot 8-bit di
  DepositScan. Le mediane coincidono su tutti e 8 i casi disponibili
  (158/158, 159/159.3, 161/161.3, ...). ImageJ, di cui DepositScan e' una
  macro, media i canali senza pesi.
- **ROI rettangolare**: usare il bounding box invece della sagoma ritagliata
  riproduce l'`Image area` riportata (22.85 vs 22.87, 24.54 vs 24.80 cm²).
- **Soglia inclusiva**: la maschera binaria cosi' ottenuta coincide con
  l'output binarizzato di DepositScan sulla stessa card (6.63% vs 6.64%).
- **Filtro sulle particelle**: `ParticleAnalyzer` viene costruito senza filtro
  di dimensione (`minSize=0`), ma `DropResultsFrame` scarta poi i record con
  `actualSize <= 50 µm`. A 600 dpi equivale a ignorare le particelle di 1-2 px
  (2 px -> 43.97 µm, 3 px -> 52.84 µm).
- **Coverage e conteggio** si calcolano sui soli record sopravvissuti a quel
  filtro, non su tutti i pixel sotto soglia.

## Algoritmo DV / volume

Ricavato dal bytecode di `DropResultsFrame$DropRecord`:

    area       = pixelArea * 42.3333 * 42.3333       // px -> µm²
    ds         = sqrt(1.2732395447351628 * area)     // = sqrt(4A/pi)
    actualSize = 0.95 * pow(ds, 0.91)                // spread factor
    volume     = pi * pow(actualSize, 3.0) / 6.0     // µm³

I record vengono ordinati per area crescente (`DropRecord.compareTo`), si
accumula il volume e DV0.1/0.5/0.9 sono i diametri dove il volume cumulato
raggiunge 10/50/90%, interpolando linearmente tra i due punti adiacenti
(`findPCTValue`). Se il target cade sotto il primo punto, il plugin interpola
dall'origine: `target * d[0] / pct[0]`.

`µL/cm² = volumeTotale * 0.1 / areaROI(µm²)`, `IMAGE AREA = W*H*42.3333²/1e8`.

La costante `PIXEL_TO_UM = 42.3333` e' cablata nel plugin: DepositScan assume
sempre 600 dpi. Le costanti dello spread factor sono di Salyani & Fox (1994).
Nessun parametro e' stato adattato ai dati.

## Lettura delle etichette

Le etichette usano un font monospace fisso e un alfabeto di 15 caratteri, per
cui il riconoscimento avviene per confronto con template ricavati dai fogli di
riferimento (`tools/build_label_templates.py` -> `src/label_templates.npz`),
non con un OCR generico. E' piu' accurato su questo font e non richiede
dipendenze esterne, cosi' l'eseguibile resta autonomo.

Ogni posizione dell'etichetta e' vincolata ai soli caratteri ammessi dal
formato, il che elimina le confusioni fra glifi simili; la direzione (`UP` /
`DW`) e' decisa sulla coppia, non carattere per carattere. Sui 24 casi di
riferimento: 24/24 corrette, identiche a quanto leggeva Tesseract.

**Limite noto:** i template coprono solo le cifre presenti nei fogli di
riferimento (1-4). Un'etichetta che contenga 0 o 5-9 verrebbe ricondotta alla
cifra piu' somigliante fra quelle note, senza segnalazione. Per estendere:
aggiungere a `tools/build_label_templates.py` un foglio che contenga le cifre
mancanti e rigenerare il file dei template.

## Punto aperto: scansioni degradate

Due card di `PROVA_A_0030` (`H3 V DW A`, `H4 V DW A`) hanno un gradiente di
illuminazione: lo sfondo giallo scende sotto 127 e viene contato come
deposito, gonfiando il Coverage (38 contro 15 e 8.5 attesi). Il conteggio dei
depositi resta invece attendibile.

Il software le rileva da solo e le marca `SFONDO_SOTTO_SOGLIA` nella colonna
`quality_flag`. Servono **due** condizioni insieme:

1. `largest_component_frac > 0.10`: un singolo oggetto occupa piu' del 10%
   della ROI (degradate 26.2-28.2%, la piu' alta tra le valide 4.5%);
2. `background_floor_gray < 143`: il livello della carta nella zona peggio
   illuminata scende verso la soglia di 127 (degradate 136-138, la piu' bassa
   tra le valide 147). Si misura come 5° percentile dei massimi su blocchi di
   64 px: il massimo locale e' la carta, il percentile ignora i blocchi
   interamente coperti dal deposito.

La prima condizione da sola non basta: su card molto bagnate le gocce si
fondono in una macchia unica legittima. `H2P1R1MUPA` ha il 41% di copertura ed
e' valida. Entrambi i valori finiscono nel CSV, cosi' si vede sempre perche' il
flag e' scattato — e se scatta troppo spesso, quale delle due condizioni
regolare (`MAX_COMPONENT_FRAC`, `MIN_BACKGROUND_GRAY` in
`src/deposit_metrics.py`).

Non e' stata applicata alcuna correzione ai dati: le scansioni degradate vanno
rifatte.

## Nota sui metadati

Il valore 200 presente nell'Excel di riferimento e' il volume di applicazione
del trattamento (200 L/ha), un dato agronomico esterno a DepositScan. Non
entra in alcun calcolo di questa pipeline.
