# Audit del branch demo (09-10-2026)

Branch `demo/pianificazione-automatica` dopo il rebase su main (migration 067-077), contro una copia del
DB del demo del 09-10 (13.806 ordini, 13 veicoli, 58 punti di ritiro, 2 company). Tutto in Docker
(`python:3.11` + `postgres:17`), Nominatim e OSRM finti, rete isolata per il test delle rotte.

## Sintesi

| Area | Esito |
|---|---|
| Test unitari BE | **1050 passati**, 1 xfail (bug noto, vedi M5), 0 falliti. Coverage 95% |
| Test unitari FE, lint, build, `npm audit` | **590 test passati** (34 file), lint pulito, build ok, **0 vulnerabilità** |
| Stress pianificazione (create, concurrent, hot, fill, spill, guasti) | **0 violazioni** sugli 8 invarianti del DB |
| Precarichi (`accepts_preloads`) | 24 scenari / 88 controlli, **0 KO**; il filtro non peggiora le prestazioni |
| Rotte HTTP (122 rotte x 8 attori x input malformati) | 0 fughe tra company, 0 rotte aperte per errore, **130 punti con eccezioni non gestite**, 1 mass assignment (M6) |
| Prestazioni | **`/check-constraints` troppo lento** (5-6 s, fino a 22 s con latenza realistica) |

Problemi, in ordine di priorità: 2 alti (A1, A2), 5 medi (M1-M4, M6), M5 già noto e alcuni bassi.

## Stato delle correzioni (stesso branch)

| Punto | Stato |
|---|---|
| A1 data del cliente | **Corretto**: `dpc` e fasce passano per il cliente solo con la pianificazione automatica attiva. Rimisurato: 19 modifiche su 20 salvate (l'altra senza fasce libere), invarianti tutti OK |
| A2 `/check-constraints` | **Ridotto**, non risolto: da 2.128 a 795 query (memo per richiesta di blocco precedente, orario azienda, coordinate di veicolo e ritiri, id del borderò; una query sola per le durate dei servizi). Restano 478 query sugli ordini e 159 sulle tappe, una per blocco e giorno: serve caricarle in blocco, vedi sotto |
| M1 OSRM | **Corretto**: timeout 2 s e circuit breaker (3 guasti di fila, pausa 60 s, poi ripiego immediato) |
| M2 errori di input | **Corretto**: id non valido, campo mancante, elemento inesistente e dati non validi rispondono con il motivo e non mandano Telegram. Resta HTTP 200 `status: ko` come il resto dell'app. Ogni altra eccezione va all'handler di prima |
| M3 unicità `schedule` | Non fatto: l'indice unico fallisce se nel DB reale ci sono duplicati, va prima controllato |
| M4 operatori | Non fatto: serve una decisione di prodotto |
| M5 `set_all_users` | **Corretto** (e tolto l'xfail dal test) |
| M6 campi riservati | **Corretto**: il cliente non può impostare conferma, esito, note interne, campi esterni né veicolo alla creazione |

I numeri della sezione "Problemi" qui sotto sono quelli misurati prima delle correzioni.

## Problemi

### A1. Il cliente non può cambiare la data di un ordine (alto, bug reale)
`restrict_order_update` ([crud.py](../src/end_points/orders/crud.py)) lascia al cliente solo `addressee, address, cap,
floor, elevator, addressee_contact, customer_note, drc, preloaded, products, version`. `dpc`,
`delivery_slot_start` e `delivery_slot_end` vengono **scartati in silenzio** e l'app risponde 200.
Misurato: 20 modifiche di data fatte dal cliente, **0 salvate** (`stress_planning lifecycle`, ora verificato sul DB).
Conseguenze:
- il form "date" su un ordine esistente sembra salvare ma non cambia niente;
- tutto il ramo di `update_order` che ricalcola fascia e borderò quando il cliente cambia la data non è mai
  raggiunto da `dpc`, ma solo da `cap` e `address`;
- lo switch "Ordine precaricato" su un ordine esistente non ha effetto da solo, perché senza `dpc` non si ricalcola nulla.

Decisione da prendere: il cliente può cambiare data? Se sì, aggiungere `dpc` e le fasce alla whitelist (e
`preloaded`, già aggiunto); se no, disabilitare il form lato FE per il cliente.

### A2. `/check-constraints` e `POST /order` lenti, vicini al timeout di gunicorn (alto)
Con latenza esterna finta di 20 ms: p50 5,7 s, p95 10,4 s, max 17 s. Con 100 ms: p50 14 s, p95 22 s
(timeout gunicorn 30 s). Un `POST /order` è arrivato a 21 s. Profilo di una chiamata (2.128 query, 5,7 s):

| Query | Numero |
|---|---|
| `SELECT delivery_coverage_entry` | 956 |
| `SELECT order` | 478 |
| `SELECT schedule` | 371 |
| `SELECT transport`, `collection_point`, `company` | 106 ciascuna |

Causa: `available_slots_by_date` valuta 53 giorni x blocchi (477 chiamate a `entry_occupied_duration`) e ognuna
rifà circa 4,5 query: blocco precedente del giorno, ordini della fascia, borderò, veicolo, azienda, punti di ritiro.
Come velocizzare, in ordine di resa:
1. Caricare in una volta sola, per la richiesta, blocchi, ordini del periodo (un `IN` su date e veicoli),
   borderò e anagrafiche, e calcolare in memoria: da ~2.100 a ~15 query.
2. Nel frattempo, cache per richiesta di `company`, `transport`, `collection_point` e di
   `previous_entry_of_day` (togliere ~1.300 query senza cambiare la logica).
3. Smettere di valutare i giorni dopo che la prima fascia valida è stata trovata, se al FE basta la data.
4. `calculate_payload_service_duration` fa una query per servizio (`.first()` in ciclo): un solo `IN`.

### M1. Dipendenza da un solo OSRM esterno senza circuit breaker (medio, non verificato in outage reale)
`OSRM_BASE_URL` è fisso su `https://osrm.fastsite.it` ([travel.py](../src/end_points/service/travel.py)), timeout 5 s per
chiamata. Nel test i guasti iniettati (20%) sono immediati e il fallback funziona (nessuna violazione), ma un
**timeout vero** vale 5 s x decine di chiamate per richiesta: `/check-constraints` supera i 30 s e il worker viene
ucciso. Non simulato: serve un OSRM che non risponde. Proposta: circuit breaker (dopo N errori, per 60 s si va diretti
al fallback Haversine), timeout 1-2 s, e la matrice `/table` solo per le tratte consecutive (oggi N x N, con
il limite OSRM di 100 coordinate che degrada a Haversine senza avvisare).

### M2. Eccezioni non gestite trasformate in HTTP 200 + messaggio Telegram (medio)
L'handler globale di generic-lib risponde `200 {"status":"ko","message":"Errore generico"}` a ogni eccezione e manda
il traceback a Telegram. L'audit delle rotte ha trovato **130 combinazioni** (rotta, punto del codice) dove input
malformato, non attaccante, genera questo comportamento:
- `int(id)` su id non numerico in quasi tutte le rotte con `<id>` (`ValueError`), e su id inesistente
  (`UnmappedInstanceError` / `AttributeError` su `None`) in 15+ DELETE/PUT che dovrebbero rispondere "non trovato";
- payload incompleto o non-oggetto: `KeyError` / `TypeError` / `AttributeError` su `POST /order/filter`,
  `/schedule`, `/user`, `/user/login`, `/check-constraints` (manca `services_id`), `/delivery-coverage`
  (manca `day_of_week`) e altre ~25;
- `POST /collection-point`, `/customer-group`, `/geographic-zone`, `/transport`, `/rae/*`: chiavi sconosciute
  nel JSON finiscono in `create(Model, request.json)` e danno `TypeError` (mass assignment non filtrato);
- `/check-constraints` con `cap` numerico: errore DB `varchar = integer`.
Effetto pratico: un client rotto o un bot riempie Telegram di allarmi e non ottiene un 400 leggibile. Proposta: un helper
`json_body(required=[...])` e `get_or_404(Model, id)` condivisi, e l'handler globale che distingue
`ValueError/KeyError` (400) dal resto (500).

### M3. `schedule` senza unicità su (data, veicolo) (medio)
Il codice assume un solo borderò per veicolo e giorno (`find_or_create_schedule`, `_schedule_stop_coord`
usano `.first()`), ma l'unicità è garantita solo dal lock applicativo. Oggi 0 duplicati, anche sotto concorrenza
(6 thread, tutti sulla stessa data). Proposta: indice unico `(company_id, transport_id, date)` dopo un controllo
dei dati esistenti.

### M4. Operatori e admin che cambiano data, CAP o indirizzo non ricalcolano fascia e borderò (medio)
Il ricalcolo è solo per `UserRole.CUSTOMER`. Se un operatore sposta un ordine pianificato, `delivery_slot_*`,
`delivery_transport_id` e la tappa nel borderò restano quelli di prima. Va deciso se è voluto (l'operatore
pianifica a mano) o se vanno almeno tolti dal borderò.

### M5. Bug noto già marcato xfail: `set_all_users`
`/service/set-all-users` confronta `User.id` con id di `ServiceUser`: i clienti già associati non sono esclusi e ricevono un
duplicato (test `test_set_all_users_should_skip_already_associated_customers`, `strict` xfail).

### M6. Il cliente può impostare campi riservati alla creazione dell'ordine (medio, verificato)
`create_order` passa al modello tutte le chiavi del payload tranne `products`, `user_id` e `cloned_order_id`, mentre
`update_order` ha una whitelist per ruolo. Provato con un cliente: `POST /order` con `confirmed`, `mark`, `operator_note`,
`external_id` e `anomaly` li salva tutti (`confirmed: true`, `mark: 5.0`, `operator_note: 'INJECTED'`, ...). Un cliente può
quindi saltare la conferma dell'operatore e scrivere nelle note interne. Preesistente a questo branch (la riga è su main).
Proposta: la stessa whitelist per ruolo di `update_order` anche in creazione.

### Bassi e osservazioni
- **Precarichi, uso**: una nuova area con `accepts_preloads` acceso non offre nessuna fascia finché il veicolo non ha già un
  ordine sullo stesso punto di ritiro (il primo ordine non può mai entrare da lì). È la regola richiesta, ma l'avvio dell'area
  dipende da ordini inseriti da altre aree o dall'operatore. Il confronto usa solo gli ordini, non le tappe di ritiro dei borderò
  creati a mano.
- **Riempimento veicoli** (`fill`, 12 ordini su due veicoli): 8 sul veicolo 1, 2 sul 2, poi 1 di nuovo sul 1. La regola "si riempie un
  veicolo alla volta" tiene, con una deviazione sull'ultimo ordine (fascia adiacente con capienza residua).
- Cache OSRM `_MATRIX_CACHE`: per processo (4 worker gunicorn = 4 cache), si svuota del tutto a 4096 voci.
- FE: bundle principale `index-*.js` da 1,99 MB (609 KB gzip) e `apexcharts` 518 KB; code-splitting per route e
  `manualChunks` per leaflet/apexcharts ridurrebbero il primo caricamento.
- Coverage BE: file sotto il 90% `end_points/orders/__init__.py` (81%), `users/session.py` (82%), `end_points/__init__.py` (83%),
  `exportation/schedule.py` (85%), `service/duration.py` (88%: il ramo OSRM non raggiungibile in `entry_transition_minutes`
  e la tappa del punto di ritiro in `_schedule_item_coord`).

## Cosa non è stato coperto
- OSRM e Nominatim veri, con latenze reali o fuori servizio (solo finti, con latenza 20/100 ms e guasti immediati).
- Gunicorn multi-processo: il carico passa dal test client di Flask, in un processo.
- I test end-to-end Playwright (`pytest -m e2e`), l'app dei corrieri, il flusso mobile, gli SMS e le email reali.
- Il flusso visivo del FE nel browser (solo test unitari, lint e build).

## Come ripetere

Script nel repo: `scripts/stress_planning.py` (scenari, incluso il nuovo `preload`), `scripts/audit_routes.py`,
`scripts/profile_check_constraints.py`. Tutti vogliono `DATABASE_URL` su una copia del dump, mai in produzione:

```bash
docker run -d --name pg -e POSTGRES_PASSWORD=pw -p 5434:5432 postgres:17
# ripristina il dump in un DB, poi sulla copia:
python -m scripts.stress_planning setup --polygon
python -m scripts.stress_planning preload --samples 10 --orders 20
python -m scripts.stress_planning lifecycle --orders 60
python -m scripts.profile_check_constraints
python -m scripts.audit_routes        # solo con la rete esterna bloccata
```
