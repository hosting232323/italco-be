# Stress test della pianificazione automatica (25-09-2026)

Branch `demo/pianificazione-automatica`, contro una copia del dump di produzione del 23-09
(13.849 ordini, migrato a 065). Nominatim e OSRM sono finti (`scripts/stress_planning.py`):
coordinate deterministiche, latenza e guasti configurabili. Copertura seminata: 48 CAP
(95% del volume), 6 veicoli a coppie sulla stessa zona, 3 fasce da 3 ore, lun-sab.

Riproduzione:

```bash
docker run -d --name italco-dump -e POSTGRES_PASSWORD=pw -p 5434:5432 postgres:17
# ripristina il dump, poi: alembic upgrade head
python -m scripts.stress_planning setup --polygon      # sul db copiato
python -m scripts.stress_planning fill --orders 12     # scenari: constraints create concurrent lifecycle fill spill
```

Le latenze sono quasi tutte CPU Python/ORM (un `select 1` costa 0,4 ms, una query ORM 5 ms),
quindi si trasferiscono a produzione meglio di quanto sembri.

## Bloccanti

### 1. La creazione ordine esplode con il numero di ordini già sulla giornata
Un `POST /order` con fascia da 0,3 s arriva a 27 s (3.813 query, 810 chiamate OSRM) già al 21° ordine
di una sessione di test; su una data "calda" (24 ordini) un singolo ordine supera il minuto.
Il tempo e' tutto in `resolve_delivery_slot` (13 s su 13 s nel profilo), la pianificazione vera
(`auto_plan_order`) costa 55 ms.

Causa: ricorsione mutua nel calcolo dell'occupazione
`entry_occupied_duration -> query_entry_orders -> _entry_fits_order -> entry_front_slot_minutes
-> entry_transition_minutes -> _entry_leftover_minutes -> entry_occupied_duration`
(106 chiamate per 17 valutazioni primarie nel profilo). Ogni livello rifà query, geocoding e OSRM
e la profondità cresce con fasce per veicolo, veicoli fratelli e ordini nella fascia.
Con OSRM reale (decine di ms a chiamata) 800 chiamate = ordine perso per timeout.

### 2. `/check-constraints` costa ~8.000 query e ~40 s anche a giornate vuote
Un cliente, nessun ordine pianificato: 8.172 query, 212 chiamate OSRM, 38-48 s (gunicorn ha
timeout 30 s: il worker viene ucciso). Il calcolo è duplicato: `check_delivery_coverage` e
`check_delivery_coverage_slots` fanno entrambi `available_slots_by_date` (62 giorni x fasce x
veicoli) sulla stessa richiesta. Con l'indirizzo, `query_entries_for_cap` ri-geocodifica e ricarica
tutti i poligoni a ogni giorno.

### 3. Il veicolo scelto dalla capienza non è quello che riceve l'ordine
L'ordine salva solo la fascia (start/end), non il veicolo. `resolve_delivery_slot` sceglie il
veicolo con la partizione virtuale di `query_entry_orders`, ma `find_coverage_entry` rifà la ricerca
con `.first()` senza `ORDER BY` e prende un veicolo qualunque tra quelli con stessa fascia e CAP.
Scenario `fill`: due veicoli sulla stessa zona, capienza 180 min, 12 ordini -> 12/12 sul veicolo 1,
veicolo 2 vuoto, borderò a 490 min su 180. Su tutto il run: veicoli {1: 4, 3: 4, 5: 14, 6: 3}.
La regola "si riempie prima un veicolo poi il successivo" vale solo sulla carta.

### 4. Ordine con fascia assegnata ma fuori da ogni borderò (spillover)
Se la fascia richiesta e' satura, `_entry_with_residual_capacity` assegna la fascia *adiacente*
dello stesso veicolo senza guardarne i CAP. `find_coverage_entry` poi cerca fascia+CAP dell'ordine,
non trova nulla e `auto_plan_order` esce con un warning: l'ordine resta "pianificato" (ha lo slot)
ma non e' in nessun borderò. Scenario `spill`: il primo ordine finisce 10:00-11:00 sul CAP 70999,
`nel borderò=False`. Succede ogni volta che fasce adiacenti dello stesso veicolo hanno CAP diversi.

### 5. Il cliente che cambia la data lascia l'ordine nel borderò vecchio
`update_order` ricalcola la fascia se cambiano `dpc`/`cap`, ma non sposta né rimuove la tappa:
scenario `lifecycle`, 5 ordini spostati su 5 restano su un borderò di data diversa dalla nuova dpc,
uno con orario di tappa diverso da quello dell'ordine. Lo stesso vale per il cambio di `cap`.

### 6. Il lock globale serializza tutta l'attività e tiene il lock durante le chiamate esterne
`create_order` prende `pg_advisory_xact_lock(736214, 1)` (lo stesso di import, PUT ordine, catalogo
servizi, di **tutte le company**) prima di geocoding e OSRM. Scenario `concurrent` (4 thread, date
diverse): 24 ordini in 19 s, p50 3,2 s per ordine con 0,8 s di lavoro reale; sui bloccanti 1-2
significa che un solo ordine lento ferma tutti e 4 i worker gunicorn. Il lock evita le gare
(nessun borderò duplicato in nessun run), quindi va tolto solo dopo aver risolto 1 e 3.

## Importanti

- **Resilienza al geocoder incoerente.** `duration.py` degrada a 0 se Nominatim cade, ma
  `resolve_delivery_slot`/`query_entries_for_cap`, `find_coverage_entry` e `optimize_schedule_stops`
  (`_coord_for`) no: con il 15% di guasti 3 ordini su 30 sono stati rifiutati con "Errore generico"
  (l'ordine del cliente perso) e uno ha lo slot senza tappa. `/check-constraints` risponde ko.
- **Il server non impone capienza né copertura.** Con dpc forzata (o due clienti nello stesso istante
  prima del lock) `chosen = effective or entries[0]` accetta comunque: 12 ordini su una fascia da
  3 ore. La disponibilita' e' solo consigliata dalla UI.
- **In produzione 189 servizi su 217 non hanno `duration`** (NULL): la capienza non si satura mai
  per i servizi e conta solo il percorso. Prima di accendere la pianificazione va valorizzata.
- **`GET /collection-point` geocodifica tutti i punti a ogni lettura** (thread pool da 10, cache per
  processo): a freddo sono N chiamate Nominatim per aprire il form ordine.
- `split_large_group.cluster_orders_by_cap`: `caps` scarta gli item senza CAP ma poi fa `zip(order_items,
  coords)`, quindi con un CAP vuoto le coordinate si spostano di una posizione su tutti gli ordini dopo.
- `transport.sync_transport_users`: `user_ids` non e' validato (ruolo DELIVERY, stessa company).
- `delete_transport` non controlla i `Product.transport_id`: FK error 500 invece di un messaggio.

## Senza problemi rilevati

Nessun borderò duplicato per (data, veicolo), nessun indice di tappa duplicato o con buchi,
nessun ordine in piu' tappe, in 6 run (sequenziale, 4 thread, guasti, lifecycle, fill, spill).

La suite unit esistente e' verde (922 passed, 1 xfailed, coverage 96%) e non intercetta nessuno dei
punti sopra: i test coprono le funzioni una a una, mai la loro composizione su una giornata piena.

---

## Esito dopo le correzioni (branch `fix/automatic-planning-stress-findings`)

Stessi scenari, stessa copia del dump, migrazione 066 applicata.

| Scenario | Prima | Dopo |
| --- | --- | --- |
| create, 25 ordini sequenziali | max 27,5 s/ordine, 2.110 chiamate OSRM | 120 ordini, max 1,3 s/ordine, 590 chiamate OSRM |
| `/check-constraints`, giornate vuote | 8.172 query, 212 OSRM, ~42 s | 1.597 query, 1 OSRM, ~4,7 s |
| fill (2 veicoli, 12 ordini) | 12/12 sul veicolo 1, 490 min su 180 | ordini ripartiti tra i due veicoli, nessuna fascia sopra capienza |
| spill (fascia adiacente con altri CAP) | ordine con fascia e senza borderò | ordine nel borderò |
| lifecycle (cambio data) | 5/5 nel borderò vecchio | 13/13 spostati, nessun disallineamento |
| guasti 15% su Nominatim/OSRM | 3/30 "Errore generico", 1 senza tappa | 0 errori, invarianti a posto |
| concurrent (4 thread) | nessuna gara | nessuna gara |

Cosa e' cambiato:

1. **Veicolo salvato sull'ordine** (`order.delivery_transport_id`, migration 067). La capienza legge gli
   ordini del veicolo e della fascia: la ripartizione virtuale tra blocchi sovrapposti, e con lei la
   ricorsione, non esistono piu'. `find_coverage_entry` usa quel veicolo (non piu' `.first()`) e non
   richiede piu' che la fascia copra il CAP, quindi anche lo spillover sulla fascia adiacente viene
   pianificato. Gli ordini con fascia ma senza veicolo restano attribuiti al primo blocco per priorita'.
2. **`resolve_delivery_entry`** restituisce il blocco scelto; se il giorno e' coperto ma non c'e' piu'
   capienza solleva `SlotUnavailableError` e `create_order`/`PUT /order` rispondono `ko` invece di
   caricare la fascia oltre la capienza. `resolve_delivery_slot` resta come wrapper.
3. **`/check-constraints`** calcola le fasce una volta sola (le date sono le loro chiavi), risolve i blocchi
   del CAP una volta e non per ogni giorno, e le durate OSRM tra gli stessi punti si memorizzano
   (`travel_time_matrix_osrm`, solo le risposte riuscite).
4. **Cambio data/CAP/indirizzo/fascia del cliente**: `unplan_order` toglie la tappa dal borderò vecchio
   (con i ritiri che servivano solo a lei) e l'ordine viene ripianificato in quello nuovo. Il form che
   rimanda gli stessi valori non sposta niente.
5. **Geocoder giu'**: `get_lat_lon_by_address/cap` degradano a `(None, None)` senza mettere il guasto in
   cache; tutti i chiamanti (fascia, borderò, ordine di visita) ereditano la resilienza. L'indirizzo
   dell'ordine si geocodifica prima di prendere il lock, non dentro.
6. **Punto di ritiro**: `lat`/`lon` salvati (creazione, modifica dell'indirizzo, backfill alla prima
   lettura) invece di geocodificare a ogni lista.
7. `split_large_group` riaggancia le coordinate all'ordine giusto; `transport` valida `user_ids` (ruolo
   DELIVERY della company) e rifiuta l'eliminazione se ci sono prodotti collegati.

Non risolvibile dal codice: 189 servizi su 217 senza `duration` in produzione (va valorizzata prima di
accendere la pianificazione), e il lock advisory resta globale (ora lavora ~0,3 s invece di decine).
