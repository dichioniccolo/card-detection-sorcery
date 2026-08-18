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
4. conversione 8-bit con **media non pesata** dei canali `(R+G+B)/3`
5. soglia **inclusiva** a 127: deposito = pixel `<= 127`
6. componenti connesse (8-connettivita', area `>= 3 px`)
7. metriche sul **bounding box** della card, a 600 DPI

## Stato di validazione

Riferimento: 24 card reali con risultati DepositScan noti. Le due card
degradate di `PROVA_A_0030` sono escluse dalle statistiche (vedi sotto).

| Metrica | Bias | MAE | Stato |
|---|---|---|---|
| Coverage | -0.07 pp | 0.19 pp | validata |
| Image area | -0.03 cm² | 0.34 cm² | validata |
| Total deposit counted | 0.00 % | 0.56 % | validata |
| Deposits/cm² | +0.16 % | 1.58 % | validata |
| DV01 | -0.46 % | 0.81 % | validata |
| DV05 | -0.31 % | 0.50 % | validata |
| DV09 | -0.35 % | 0.49 % | validata |
| µL/cm² | -1.16 % | 2.30 % | validata |

I quattro parametri non documentati nel paper sono stati ricavati dai dati:

- **Conversione 8-bit**: verificata direttamente contro gli screenshot 8-bit di
  DepositScan. Le mediane coincidono su tutti e 8 i casi disponibili
  (158/158, 159/159.3, 161/161.3, ...). ImageJ, di cui DepositScan e' una
  macro, media i canali senza pesi.
- **ROI rettangolare**: usare il bounding box invece della sagoma ritagliata
  riproduce l'`Image area` riportata (22.85 vs 22.87, 24.54 vs 24.80 cm²).
- **Soglia inclusiva**: la maschera binaria cosi' ottenuta coincide con
  l'output binarizzato di DepositScan sulla stessa card (6.63% vs 6.64%).
- **Area minima 3 px**: azzera il bias sul conteggio (+0.02%, MAE 0.81%);
  corrisponde al parametro *Size* di Analyze Particles.

## Algoritmo DV / volume

DV01/DV05/DV09 e µL/cm² usano le equazioni pubblicate di DepositScan
(Zhu, Salyani & Fox 2011), implementate in `src/deposit_metrics.py`:

    ds = sqrt(4A/pi)          (Eq. 2)  diametro macchia, A in µm²
    d  = 0.95 * ds^0.910      (Eq. 1)  spread factor carta idrosensibile
    d  = 1.06 * A^0.455       (Eq. 3)  forma finale, equivalente
    Vi = pi * di^3 / 6        (Eq. 4)  volume goccia
    Vj = somma cumulata       (Eq. 5)
    %Vj = Vj / VN * 100       (Eq. 6)

DV0.1/0.5/0.9 = diametri dove %Vj vale 10/50/90, con interpolazione lineare
tra i due punti adiacenti. µL/cm² = volume cumulato totale / area analizzata.

Le costanti dello spread factor sono di Salyani & Fox (1994), verificate dagli
autori con gocce di dimensione nota da un generatore di gocce singole.
Nessun parametro e' stato adattato ai dati: sono tutte costanti pubblicate.

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
