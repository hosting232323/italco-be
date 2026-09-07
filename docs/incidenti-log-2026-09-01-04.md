# Incidenti osservati nei log del 1–4 settembre 2026

Documento di diagnosi, creato il 4 settembre 2026. Raccoglie gli incidenti diversi dall'importazione Excel e dall'incompatibilità fra tipo ordine e tipi dei servizi, trattati separatamente nell'audit dati. Non è una certificazione dello stato attuale di produzione.

## Fonti, copertura e recupero dei log

File analizzati: `2026-09-01.jsonl`, `2026-09-02.jsonl`, `2026-09-03.jsonl`, `2026-09-04.jsonl`, consegnati localmente in `C:/Users/vanni/Downloads/`. Ogni riferimento `file:riga` usa la numerazione fisica del file a partire da 1. Gli orari sono quelli del campo `ts`, Europe/Rome (`+02:00`). Il file del 4 settembre termina alle **09:56:26**, non a fine giornata.

Il corpus contiene 9.929 eventi (3.435 / 2.897 / 3.378 / 219 per giorno). 927 risposte sono troncate nel JSONL originale: cercare nel `preview` può individuare un evento, ma non consente di ricostruire le parti mancanti. I file caricati, lo stato delle schede browser e il commit del container non sono inclusi.

La migrazione `src/database/alembic/versions/043_remove_logs.py`, funzione `migrate_logs_to_files`, documenta il percorso dei log: `<STATIC_FOLDER>/prod/logs/YYYY-MM/YYYY-MM-DD.jsonl` (`test` al posto di `prod` in sviluppo). Verificare il valore effettivo di `STATIC_FOLDER` e `IS_DEV` del deployment. `src/__init__.py` legge `STATIC_FOLDER`; `gitlab/deploy.yml` monta quella directory persistente nel container. Non confondere questi file di richieste/risposte con il solo stdout di `docker logs`. Per i log runtime, verificare anche la versione di `generic_lib`/hook installata nel container.

I file si possono scaricare dalla pagina di amministrazione dei log già usata per l'analisi, oppure recuperare dalla directory persistente del server. Non assumere un nome fisso di container: il deployment usa i suffissi blue/green.

Ricerca rapida sui file locali, senza stampare interi payload:

```powershell
rg -n -o -g '2026-09-*.jsonl' 'InvalidTextRepresentation|UndefinedError|NoneType|NotFoundError|collection_point|21291|21283|modificato nel frattempo' C:/Users/vanni/Downloads
```

Se la shell non espande il glob per `rg`, passare la directory con `-g '2026-09-*.jsonl'`. Per leggere un singolo evento in Python e mostrare solo dati diagnostici:

```python
import json
from pathlib import Path
file = Path.home() / 'Downloads' / '2026-09-03.jsonl'
line = 2804
record = json.loads(file.read_text(encoding='utf-8-sig').splitlines()[line - 1])
print(record['ts'], record.get('user_id'), record['request']['method'], record['request']['path'])
print(record.get('response', {}).get('message'))
print(record.get('response', {}).get('traceback'))
# Il body può essere request.json oppure JSON serializzato in request.form.data.
```

Gli hash degli input, riportati qui sotto, permettono di verificare che righe e conteggi si riferiscano agli stessi file:

| File | SHA-256 |
|---|---|
| 2026-09-01.jsonl | `3950332f5b1af073b0794682862e190115a4231dbfd9124d47941d138808258a` |
| 2026-09-02.jsonl | `9720d6bce698cf784837d048061f8b1072a2120c1fc9fb53fd26da883ff084cc` |
| 2026-09-03.jsonl | `106da911721c43dc93ba1c8f7f7d4b0654806e619863251285cf2aea243a90ef` |
| 2026-09-04.jsonl | `c7649dea9f7a01571dd28499d4543935b3a525961bb8eeafea806467c626d8c5` |

## Intervalli degli eventi esclusi dall’audit Excel/tipi

I conteggi sono richieste, non utenti o incidenti distinti. Un medesimo errore può essere ritentato molte volte.

| Messaggio/famiglia | N. | Primo evento | Ultimo evento | Prima prova |
|---|---:|---|---|---|
| L'ordine è stato modificato nel frattempo. Ricarica la pagina e riprova. | 35 | 2026-09-01T09:00:19.936067+02:00 | 2026-09-03T13:12:36.162036+02:00 | `2026-09-01.jsonl:148` |
| Servizio con codice 'CONSEGNA FASCIA 1 (LAVATRICI)' non trovato per il punto vendita selezionato | 2 | 2026-09-01T09:20:50.361629+02:00 | 2026-09-03T23:18:56.455991+02:00 | `2026-09-01.jsonl:282` |
| Ruolo non autorizzato | 22 | 2026-09-01T09:30:52.350617+02:00 | 2026-09-04T09:04:30.090769+02:00 | `2026-09-01.jsonl:370` |
| Borderò non trovato | 3 | 2026-09-01T09:45:06.189403+02:00 | 2026-09-01T09:56:31.942574+02:00 | `2026-09-01.jsonl:460` |
| sqlalchemy.exc.DataError: (psycopg2.errors.InvalidTextRepresentation) invalid input syntax for type integer: "1.5" | 101 | 2026-09-01T11:04:13.439462+02:00 | 2026-09-02T13:01:24.458871+02:00 | `2026-09-01.jsonl:1025` |
| Hai selezionato degli ordini che non sono in stato Booked | 3 | 2026-09-01T11:48:38.006477+02:00 | 2026-09-03T06:37:26.201019+02:00 | `2026-09-01.jsonl:1466` |
| Credenziali errate | 22 | 2026-09-01T13:24:30.011648+02:00 | 2026-09-03T22:35:36.906283+02:00 | `2026-09-01.jsonl:2595` |
| Nickname già in uso | 1 | 2026-09-01T13:29:58.595339+02:00 | 2026-09-01T13:29:58.595339+02:00 | `2026-09-01.jsonl:2655` |
| Rifiuto con dependencies | 1 | 2026-09-01T13:30:31.693362+02:00 | 2026-09-01T13:30:31.693362+02:00 | `2026-09-01.jsonl:2661` |
| jinja2.exceptions.UndefinedError: 'dict object' has no attribute 'collection_point' | 9 | 2026-09-01T16:56:06.550469+02:00 | 2026-09-01T17:24:49.191830+02:00 | `2026-09-01.jsonl:3146` |
| Servizio con codice 'consegna e/o ritiro da/a assistenza tecnica' non trovato per il punto vendita selezionato | 1 | 2026-09-01T17:46:33.290166+02:00 | 2026-09-01T17:46:33.290166+02:00 | `2026-09-01.jsonl:3317` |
| Utente già associato al servivizio | 1 | 2026-09-01T17:47:16.062904+02:00 | 2026-09-01T17:47:16.062904+02:00 | `2026-09-01.jsonl:3318` |
| AttributeError: 'NoneType' object has no attribute 'id' | 3 | 2026-09-03T15:48:42.177411+02:00 | 2026-09-03T15:48:48.075241+02:00 | `2026-09-03.jsonl:2804` |
| openai.NotFoundError: Error code: 404 | 1 | 2026-09-03T17:54:33.058273+02:00 | 2026-09-03T17:54:33.058273+02:00 | `2026-09-03.jsonl:3197` |
| Accesso Delivery non disponibile dal gestionale: usa l'app Ares Delivery | 3 | 2026-09-04T09:30:10.889752+02:00 | 2026-09-04T09:30:30.639594+02:00 | `2026-09-04.jsonl:54` |

## 1. Piano "1.5" inviato a una colonna intera — 101 eccezioni

**Prove:** primo evento `2026-09-01.jsonl:1025`, ultimo `2026-09-02.jsonl:1137`. Tutti i 101 payload contengono **`floor: "1.5"`**; PostgreSQL risponde `invalid input syntax for type integer: "1.5"` durante la creazione dell'ordine.

**Causa:** il campo Piano del frontend usa `positiveNumberRules`, che ammette qualsiasi numero non negativo, compreso 1.5. Il formatter mantiene quella stringa; il backend la inoltra alla colonna `Order.floor = Column(Integer)` senza una validazione adeguata.

**Riproduzione:** compilare un ordine valido con Piano `1.5`. La prova esegue davvero la regola JavaScript e conferma che accetta il valore. Il rifiuto PostgreSQL è attestato nei log; non è stato avviato un database PostgreSQL per rieseguirlo.

**Correzione:** decidere il dominio del campo. Se il piano deve essere intero, validarlo esplicitamente sia nel frontend sia nel backend e restituire un errore del campo. Se i mezzi piani sono ammessi, adeguare lo schema e la logica di calcolo. Non arrotondare silenziosamente.


## 2. Esportazione PDF con prodotto sul mezzo — 9 eccezioni

**Prove:** `2026-09-01.jsonl:3027` mostra l'ordine **21283** con prodotto dotato di **transport**, privo di **collection_point**. Le esportazioni falliscono alle righe `3146,3156,3164,3192,3202,3212,3225,3231,3272`.

**Causa:** il template storico `templates/components/order.html:48` legge incondizionatamente `product.collection_point.name`. Il serializzatore `add_service` può invece produrre `transport` al posto di `collection_point`: è una forma di dati prevista dal codice.

**Riproduzione:** invocare la macro Jinja `products_table` con un prodotto che ha `services` e `transport`, senza `collection_point`. Riprodotta esattamente la `UndefinedError` con il template storico. Il template corretto in `be5b1c8` rende lo stesso oggetto senza eccezioni.

**Stato:** una correzione è già presente nel codice locale analizzato. I log provano il guasto della versione storica, non la versione oggi distribuita.


## 3. Upload foto su ordine di un'altra azienda — 3 eccezioni

**Prove:**

- `2026-09-03.jsonl:2743`: utente **70**, ruolo Admin, **company_id 2**.
- `2026-09-03.jsonl:2804–2806`: quell'utente invia un aggiornamento multipart dell'ordine **21291**, **company_id 1**, versione 3.
- Il traceback mostra che `get_by_id` ha restituito **None**, poi `handle_photos` tenta `order.id`.
- `2026-09-03.jsonl:2812,2813,2825`: logout, login dell'utente **1**, aggiornamento dello stesso ordine riuscito, versione 4.

**Causa del crash dimostrata:** manca il controllo dell'esistenza/accessibilità dell'ordine prima di elaborare le foto. Il filtro per azienda in `database/events.py` e lo scope di `flask_session_authentication` spiegano il mancato risultato per l'utente 70. Il salvataggio successivo prova che l'ordine non era semplicemente assente dal sistema.

**Riproduzione:** eseguire `handle_photos` con un upload immagine e `order=None`; riprodotto l'accesso a `order.id`. In un ambiente di integrazione, usare un utente di company 2 e un ordine di company 1 per esercitare anche la query con scope.

**Limite:** non è possibile stabilire da questi log come quel browser abbia ottenuto o conservato il payload dell'altra azienda: cache rimasta dopo cambio account, altra scheda e altri percorsi di lettura richiedono stato del browser o tracciamento aggiuntivo. Il commit frontend `6f6b4c1` contiene già il reset degli store al logout; non prova che quella versione fosse caricata nel browser dell'incidente.

**Correzione:** validare ordine accessibile prima di upload, version check e aggiornamento; resettare lo stato al cambio account/azienda e verificare anche i percorsi di lettura. Non rimuovere il filtro per azienda per far riuscire l'upload.


## 4. Chatty: creazione thread Assistants restituisce 404 — 1 eccezione

**Prova:** `2026-09-03.jsonl:3197`, `POST /chatty/chat`: il crash avviene in **`client.beta.threads.create().id`**, prima di cercare l'ordine citato nel messaggio. Quindi il 404 non indica che l'ordine 21297 sia inesistente.

Il codice distribuito nell'evento usa la vecchia Assistants API. La [documentazione ufficiale OpenAI sulle dismissioni](https://developers.openai.com/api/docs/deprecations#2025-08-20-assistants-api) indica la rimozione dell'API il **26 agosto 2026**, prima dell'evento. L'integrazione obsoleta è dimostrata; la dismissione è una spiegazione fortemente supportata del 404. Il log non include URL/base URL e corpo della risposta remota, perciò non consente di certificare ulteriori dettagli della risposta del provider.

**Correzione:** migrazione a Responses/Conversations e gestione esplicita degli errori esterni. Una modifica locale in tal senso era già presente, non ancora committata, e non è stata toccata. Non ho effettuato richieste OpenAI a pagamento né simulato un test end-to-end del provider.


## 5. Altri rifiuti registrati: inventario e limiti

| Risposta | Numero | Interpretazione e riproduzione |
|---|---:|---|
| Ordine modificato nel frattempo | 35 | Il client invia una versione diversa da quella nel DB. Riproducibile aprendo lo stesso ordine in due sessioni, salvando nella prima e poi nella seconda. I log non identificano per ogni evento quale scrittura abbia incrementato la versione. |
| Servizio PDF non trovato | 3 | Mancata associazione cliente/codice. Due casi riguardano `CONSEGNA FASCIA 1 (LAVATRICI)`, uno `consegna e/o ritiro da/a assistenza tecnica`, tutti per cliente 83. Il 3/9 alle righe 3340–3345 il primo fallisce, viene creato servizio 225 e associato al cliente con il codice esatto, poi l'import riesce. |
| Ruolo non autorizzato | 22 | Chiamate a `/dashboard/analytics` da ruoli non ammessi. Esempio `2026-09-01.jsonl:370`, utente 14. Il backend rifiuta correttamente; il frontend deve evitare richieste non disponibili per quel ruolo. |
| Credenziali errate | 22 | Fallimento autenticazione; non è possibile distinguere ogni caso fra utente non trovato e password errata dal messaggio aggregato. |
| Borderò non trovato | 3 | Letture di `/schedule/1430/position` il giorno 1, righe 460,461,603. Non è dimostrata la causa storica della non accessibilità del borderò. |
| Ordini non in stato Booked | 3 | La pianificazione rifiuta gli ID che non soddisfano la precondizione di stato. |
| Accesso Delivery non disponibile dal gestionale | 3 | Blocco esplicito del login web Delivery, previsto dal codice; usare il canale applicativo previsto. |
| Nickname già in uso | 1 | Vincolo di unicità dell'utente. |
| Utente già associato al servizio | 1 | Associazione già presente; non equivale alla presenza del codice richiesto da un'importazione. |
| `ko` con sole dipendenze | 1 | `DELETE /user/85`, `2026-09-01.jsonl:2661`. È il controllo preliminare prima della cancellazione: l'endpoint senza `force` restituisce questo oggetto anche con conteggi zero. Non è un crash. |
| Sessione/token | 449 | 245 token assenti, 187 scaduti, 16 sessioni assenti, 1 non valida. Comprendono i normali passaggi di login/refresh: non vanno equiparati a 449 guasti. |


## Dove intervenire e come riprodurre

| Caso | Backend | Frontend / riproduzione |
|---|---|---|
| Piano decimale | `src/database/schema.py`: `Order.floor`; `src/end_points/orders/crud.py`: `create_order` | `src/components/orders/OrderOperatorForm.vue`, `src/utils/validation.js`: `positiveNumberRules`; `src/stores/order.js`: `formatBody`. Inviare un ordine valido con `floor: "1.5"`. |
| PDF senza punto di ritiro | `templates/components/order.html`: `products_table`; `src/end_points/exportation/order.py`: `export_order`; `src/end_points/orders/queries.py`: `add_service` | Renderizzare un prodotto con `transport` e senza `collection_point`. La vecchia macro fallisce; la guardia della correzione `be5b1c8` rende lo stesso prodotto. |
| Foto/azienda | `src/end_points/orders/__init__.py`: `update_order_endpoint`; `src/end_points/orders/photo.py`: `handle_photos`; `src/end_points/__init__.py`: `flask_session_authentication`; `src/database/events.py`: `add_company_filter` | Verificare `src/utils/logout.js` e `src/utils/tenantStores.js` in italco-fe; in ambiente isolato inviare una foto per un ordine di azienda 1 autenticandosi nell'azienda 2. L'ordine non accessibile deve essere gestito prima di elaborare l'upload. |
| Chatty | `src/end_points/chatty.py`: `send_message`; codice storico `client.beta.threads.create()` | La richiesta di creazione di una chat fallisce prima della ricerca dell'ordine. Verificare la versione distribuita e gestire esplicitamente gli errori provider. |
| Versione ordine | `src/end_points/orders/__init__.py`: confronto `version`; `src/database/events.py`: `increment_order_version` | Aprire l'ordine in due sessioni, salvarlo nella prima, poi nella seconda. Il rifiuto protegge dalle sovrascritture; il frontend deve ricaricare lo stato. |
| Import PDF/codice mancante | `src/end_points/importation/pdf.py`: `order_import_by_pdf`; `src/end_points/service/queries.py`: `get_service_user_by_user_and_code` | Caricare il PDF per un cliente senza associazione con quel codice; aggiungere la mappatura corretta e riprovare in test. Le prove storiche sono nella sezione inventario. |
| Dashboard/ruolo | `src/end_points/dashboard/__init__.py`: decoratore di autorizzazione; individuare la rotta con `rg` | `src/stores/dashboard.js`, chiamata `dashboard/analytics`; verificare il caricamento dal componente e dal login per i ruoli non ammessi. |
| Eliminazione utente | `src/end_points/users/__init__.py`: rotta DELETE, parametro `force` | La prima richiesta serve a mostrare le dipendenze e restituisce `ko` anche se tutti i conteggi sono zero. Non classificare questo evento come crash. |

Comandi per ritrovare i punti anche se le righe cambiano:

```bash
rg -n 'floor =|def create_order|def handle_photos|def update_order_endpoint|def add_company_filter|def increment_order_version' src
rg -n 'products_table|collection_point.name' templates/components/order.html
rg -n 'threads.create|responses.create|def send_message' src/end_points/chatty.py
rg -n 'get_service_user_by_user_and_code|not trovato' src/end_points/importation/pdf.py
rg -n 'analytics|flask_session_authentication' src/end_points/dashboard
```

## Stato delle verifiche e limiti

Le riproduzioni diagnostiche sono state eseguite fuori dal repository, in `C:/Users/vanni/italco-log-analysis/`: `verify_evidence.py`, `reproduce.py`, risultati JSON e snapshot Git. Per i casi qui inclusi: accettazione del piano nel vero codice JavaScript, eccezione Jinja sulla macro storica e successo sulla macro corretta, crash di `handle_photos` con ordine non disponibile. Database e storage delle riproduzioni sono simulati in memoria; non si tratta di replay HTTP su produzione. Il rifiuto PostgreSQL e la risposta OpenAI sono osservazioni dei log, non chiamate rieseguite in produzione.

Il codice locale analizzato contiene già la correzione PDF `be5b1c8`; il frontend `6f6b4c1` contiene reset degli store al logout. Chatty aveva modifiche locali preesistenti verso Responses/Conversations. Verificarne il deployment prima di dichiarare ancora aperto o risolto ciascun incidente. Non sono state modificate queste implementazioni per redigere il documento.

Per l'upload dell'altra azienda è certa la causa del crash e la differenza di contesto; non sono provati il percorso originario con cui il browser ha ottenuto i dati, la scheda coinvolta o un eventuale cambio account in un'altra scheda. Per il 404 OpenAI il log non include URL/base URL e corpo remoto. Per i rifiuti di versione e il borderò non trovato non è sempre ricostruibile l'evento precedente che ha cambiato lo stato. Queste lacune non vanno sostituite con ipotesi presentate come fatti.
