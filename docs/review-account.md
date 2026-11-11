# Account di revisione per Apple

`scripts/create_review_account.py` crea, in una company a parte, un corriere demo con i borderò pronti da
provare. Serve a far passare la revisione di App Store Connect (e quella di Google Play) su **dati
inventati**, senza toccare nessun cliente vero.

## Cosa crea

Tutto dentro la company **Revisione Apple** (senza pianificazione automatica, senza moduli attivi):

| Cosa | Dettaglio |
|---|---|
| Corriere demo | ruolo Delivery, nickname `revisore.apple` (il campo "Email o username" dell'app) |
| Veicolo | "Furgone Demo" (`DEMO01`); i borderò prendono i corrieri dal veicolo |
| Punto vendita | utente `revisore.apple.punto-vendita` (non fa login), email `punto.vendita@example.invalid` |
| Punti di ritiro | "Punto di ritiro Demo 1" (Barletta) e "Punto di ritiro Demo 2" (Bari) |
| Servizio e prodotti | "Consegna al piano Demo"; Lavatrice, Frigorifero, Lavastoviglie, Forno (tutti "Demo") |
| Borderò | uno per giorno, da 7 giorni fa fino a 30 giorni da oggi (configurabile) |

Ogni borderò ha **7 voci**: 2 ritiri, 4 consegne e 1 attività ("Pausa pranzo (demo)").
Destinatari fittizi (Rossi Mario, Bianchi Anna, Verdi Luca, Esposito Giulia, Ferrari Paolo, Romano Sara) con
indirizzi e coordinate di Barletta, Bari, Monopoli, Bisceglie, Trani e Molfetta, che ruotano di giorno in giorno.

- **Oggi e i giorni futuri**: ordini in stato *Scheduled*, voci da completare. Completati i due ritiri, le consegne
  passano a *Booking* e si possono chiudere (consegnato con foto e firma, non consegnato, da riprogrammare,
  anomalia) come in produzione.
- **Giorni passati**: voci completate e ordini consegnati, così lo "Storico" dell'app non è vuoto.

## Come si lancia (da Vanni, sul server)

Lo script legge `DATABASE_URL` dall'ambiente del container, come gli altri script. Sul server:

```bash
docker ps --format '{{.Names}}'            # trova il container del backend (italco-be-blue / -green)
docker exec -it <nome-container> python -m scripts.create_review_account --dry-run   # prima: solo simulazione
docker exec -it <nome-container> python -m scripts.create_review_account
```

A fine comando stampa **una sola volta** la password generata del corriere: copiala subito (è l'unica
volta). Non viene scritta in nessun file né nei log. Se preferisci sceglierla tu:

```bash
docker exec -it -e REVIEW_PASSWORD='...' <nome-container> python -m scripts.create_review_account
# oppure --password '...'
```

Utente e password da dare ad Apple (App Store Connect → pagina della versione → "Informazioni di accesso"):
nickname `revisore.apple` e la password.

## Opzioni

| Opzione | Default | Cosa fa |
|---|---|---|
| `--days N` | 30 | giorni di borderò da oggi (oggi compreso) |
| `--past-days N` | 7 | giorni passati già completati, per lo Storico (0 per non crearli) |
| `--company-name` | `Revisione Apple` | nome della company |
| `--nickname` | `revisore.apple` | username del corriere |
| `--password` | (casuale) | password; in alternativa la variabile `REVIEW_PASSWORD` |
| `--dry-run` | | stampa cosa farebbe senza scrivere |
| `--reset` | | elimina borderò e ordini della company di revisione e li ricrea da oggi |

## Idempotente: si può rilanciare

- **Senza `--reset`** un secondo lancio aggiunge solo i giorni che mancano fino a oggi + `--days`: non duplica
  utenti, veicolo, punti di ritiro, servizio né prodotti. Va rilanciato ogni tanto per tenere sempre dei
  giorni futuri davanti al revisore (consigliato ogni 3-4 settimane, o prima di una nuova revisione).
- **Con `--reset`** ripartono dati intatti: serve dopo che il revisore ha completato operazioni (le voci
  completate non si possono rifare). Elimina borderò, ordini, foto e storico della **sola** company di
  revisione e azzera la posizione del corriere demo. La password resta quella di prima, a meno di passarne una.

Lo script non tocca mai altre company. Si rifiuta di lavorare se la company col nome dato contiene dati che
non ha creato lui: ordini senza `external_id` che inizia per `REVIEW-` o utenti diversi dal corriere demo e dal
suo punto vendita. Si ferma anche se il nickname esiste già in un'altra company (il nickname è unico su tutta la
piattaforma): in quel caso scegline un altro con `--nickname`.

## Cose da sapere prima di consegnare l'account

1. **SMS**: gli ordini demo hanno `addressee_contact` **vuoto**. Con un numero, `delay_sms_check`
   (`orders/sms_sender.py`) invierebbe SMS veri via Vonage a ogni riprogrammazione.
2. **Email**: quando il revisore segna "non consegnato", un ritardo o un'anomalia, `mailer_check`
   (`orders/mailer.py`) manda una email agli indirizzi in `MAILS` (oggi il Gmail operativo nel codice) e
   all'email del cliente collegato all'ordine. Il cliente demo ha `@example.invalid` (dominio che non
   recapita), ma gli indirizzi di `MAILS` ricevono le email: avvisa chi le legge.
3. **Posizione**: il revisore deve concedere il permesso di localizzazione sul telefono (il testo
   nelle note per Apple lo spiega). Il borderò parte dalla posizione attivata dal banner.
4. **Date**: i borderò sono legati alla data di oggi del server. Se la revisione arriva dopo che i giorni
   futuri sono finiti, l'app mostra "Nessun ordine trovato": rilancia lo script.

## Dopo l'approvazione

Tutti i dati demo stanno dentro la company "Revisione Apple" (nessun cliente, punto di ritiro o ordine reale
e' stato toccato): per toglierli basta eliminare quella company e i suoi dati dal database, oppure lasciarla
in modo che l'utente `revisore.apple` resti disponibile per le prossime revisioni. Non esiste (ancora) un
comando di eliminazione completa: `--reset` ricrea i borderò ma lascia la company.
