# Replica indipendente di DepositScan

Da JPG di fogli A4 scansionati (4 sticky card ciascuno) produce un CSV con
metadati e metriche di deposito per ogni card.

## Uso

GUI:

```bash
venv/bin/python3 gui.py
```

Riga di comando:

```bash
venv/bin/python3 main.py assets/PROVA_A_0027.jpg [altri.jpg ...] -o output.csv
```

Richiede `tesseract-ocr` installato a livello di sistema.

## Pipeline

1. rilevamento della griglia prestampata (linee della tabella)
2. individuazione delle 4 card e delle 4 etichette
3. OCR dell'etichetta, validato contro il pattern `H# P# R# [M|V] [UP|DW] [A-D]`
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

## Punto aperto: scansioni degradate

Due card di `PROVA_A_0030` (`H3 V DW A`, `H4 V DW A`) hanno un gradiente di
illuminazione: lo sfondo giallo scende sotto 127 e viene contato come
deposito, gonfiando il Coverage (38 contro 15 e 8.5 attesi). Il conteggio dei
depositi resta invece attendibile.

Il software le rileva da solo: se un singolo oggetto occupa piu' del 10% della
ROI, la card viene marcata `SFONDO_SOTTO_SOGLIA` nella colonna `quality_flag`.
Sui 24 casi il criterio separa nettamente (degradate 25.8-27.8%, la piu' alta
tra le valide 4.5%). Non e' stata applicata alcuna correzione: quelle
scansioni vanno rifatte.

## Nota sui metadati

Il valore 200 presente nell'Excel di riferimento e' il volume di applicazione
del trattamento (200 L/ha), un dato agronomico esterno a DepositScan. Non
entra in alcun calcolo di questa pipeline.
