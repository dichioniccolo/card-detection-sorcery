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
| DV01 / DV05 / DV09 | — | — | **PROVVISORI** |
| µL/cm² | — | — | **PROVVISORIO** |

Come sono stati determinati i tre parametri non documentati:

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

## Punti aperti

### DV01 / DV05 / DV09 e µL/cm² — non ricostruibili dai dati attuali

Sono percentili della distribuzione **volumetrica** delle gocce. Il passaggio
mancante e' la trasformazione macchia -> goccia (*spread factor*): la macchia
sulla carta idrosensibile e' sempre piu' grande della goccia che l'ha
prodotta, con un fattore che dipende dalla dimensione.

Cosa dicono i dati disponibili:

- il rapporto tra il mio diametro-macchia e il DV di DepositScan non e'
  costante (1.8-2.2 su DV01, 2.0-3.2 su DV05), quindi lo spread factor **non**
  e' una semplice costante;
- µL/cm² correla molto bene con la somma dei cubi dei diametri di macchia
  (R² = 0.984), ma con dispersione residua del 14%: la dipendenza e' vicina a
  d³ con una correzione dimensionale;
- una legge di potenza globale `d_goccia = a · d_macchia^b` ottimizzata su
  tutti i 66 valori DV di riferimento arriva solo a MAPE 8.8% (errore massimo
  43.7%). E' un fit empirico mediocre, non la ricostruzione dell'algoritmo.

**Perche' non basta:** dall'Excel abbiamo solo 3 numeri aggregati per card.
Molte trasformazioni diverse producono gli stessi 3 percentili. Il problema e'
sottodeterminato: nessuna quantita' di analisi sulle immagini lo risolve.

**Esperimento necessario (uno solo):** in DepositScan/ImageJ, su una card con
ampia gamma di dimensioni (es. `H4 P1 R1 V UP D`), esportare la tabella
**Analyze Particles per singola particella** (Results, non Summary), a parita'
di soglia 127. Confrontando quelle aree con i DV riportati per la stessa card
la trasformazione si ricava direttamente, invece di essere ipotizzata.

Finche' non e' fatto, le colonne `*_PROVVISORIO` del CSV usano il diametro
equivalente della macchia **senza** correzione di spread factor: sono
indicative e non confrontabili con i valori DepositScan.

### Scansioni degradate

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
