## BUG BE: E' possibili assegnare servizi a utenti non customer (non dovrebbe essere possibile)

Verificato il 18/07/2026: ancora aperto. POST /service/customer crea la ServiceUser da request.json
controllando solo il duplicato, mai il ruolo dell'utente (set-all-users invece filtra i CUSTOMER).

## BUG FE: Controlli campi selector possono essere negativi (solo positivi a seconda cifra decimale)

## BUG FE: Form Delivery a disposizione per customer (rimuovere il selector dei form se customer)

## BUG FE O BE(?): Da utente customer non è possibile aprire i filtri nella dashboard

## BUG FE: Selezione piano passa stringa vuota se non è stato selezionato nessun piano (invece di mostrare un messaggio di errore o disabilitare il pulsante di conferma) dà errore in db

## BUG BE: update_schedule_item lato delivery non è transazionale

PUT /schedule/item/<id> (src/end_points/schedule/delivery.py) aggiorna l'item e poi porta più ordini
a BOOKING con sessioni implicite separate, leggendo i borderò fuori transazione: un fallimento a metà
lascia stato parziale. Stessa categoria dei fix fatti nel branch fix-schedule-log-mutation, endpoint
non ancora coperto.

## BUG BE: import Excel con date non valide -> 500 a metà import

In order_import_by_excel una data Booking/DRC non valida nel file produce DataError al commit con gli
ordini precedenti già committati. La validazione date esiste solo nel conflict endpoint: la riga con
data invalida dovrebbe finire in conflicted_orders.

## BUG BE: payload schedule malformati -> 500 invece di ko

In create/update borderò un deleted_users non-lista o elementi di users senza chiave id producono
KeyError/TypeError -> Errore generico, invece di un ko di validazione.

## BUG BE: messaggio del vincolo RAE appiattito in "Errore generico"

update_products (src/end_points/orders/services.py) solleva Exception con messaggio user-friendly
sul vincolo di eliminazione RAE, ma il gestore globale lo trasforma in "Errore generico": il
messaggio non arriva mai al client. Andrebbe convertito in ko di validazione.

## BUG BE: la rischedulazione può assegnare un trasporto storico errato

reschedule_products usa get_delivery_transport(delivery_user_id), che apre una nuova sessione e
restituisce il primo trasporto associato a un qualsiasi borderò del delivery. Se il delivery ha più
borderò storici, release_transport_id può quindi puntare al mezzo sbagliato. Il trasporto va ricavato
dal borderò collegato all'ordine corrente usando la stessa sessione della transazione.

## BUG BE: conflict Excel permette riferimenti appartenenti a clienti diversi

validate_conflict_order verifica soltanto che ServiceUser e CollectionPoint esistano. Non controlla
che i servizi e il punto di ritiro appartengano allo stesso customer, né che i servizi siano di tipo
Delivery. Un payload alterato può quindi creare ownership e visibilità incoerenti tra clienti.

## BUG BE: validazione date del conflict Excel solo sintattica

DATE_PATTERN controlla soltanto il prefisso YYYY-MM-DD e accetta valori impossibili o con suffissi,
ad esempio 2026-99-99 o 2026-07-18-spazzatura. Questi valori arrivano al flush DB e possono ancora
produrre un 500. Le date vanno interpretate semanticamente e normalizzate prima di build_order.

## BUG BE: update borderò non valida gli utenti delivery già associati

update_schedule valida solo gli utenti ricevuti nel payload e unisce successivamente gli utenti già
presenti e non eliminati. Un DeliveryGroup legacy associato a un customer/admin può quindi restare
nel borderò anche dopo un aggiornamento. La validazione va eseguita su final_user_ids o accompagnata
da una migrazione/audit delle associazioni esistenti.

## SPUNTO BE: outbox per SMS post-commit

Gli SMS ora partono dopo il commit (niente più invii su transazioni poi annullate), ma senza retry:
se Vonage fallisce il client riceve 500 con dati già committati. La soluzione completa è una coda
outbox processata fuori richiesta.

# COSE VISTE

- Admin ha la possibilità di vedere nella pagina log tutte le richieste effettuate al be

- Creazione di ordine come utente customer, gestione dei servizi con tipi e utenti abilitati
- Configurazione dei vincoli sulle aree geografiche (in /customer-points Gestione Aree Geografiche )
- Configurazione Gestione Regole Punti Vendita per lo specifico customer (in /customer-points Gestione Regole Punti Vendita )
- Vincolo sulle date per gestione servizi max giornalieri (in /services)
- Impattano su data prevista da cliente in fase di creazione ordine per gli utenti customer e utente customer non può vedere la data di consegna e non può aggiungere prodotti con flag ritiro rae.

## LOGICA RAE

- Il prodotto RAE richiede la quantità
- Il proddotto RAE ha nei prodotti degli elementi predefiniti e non stringhe libere
- Accedendo come admin è possibile vedere la pagina di configurazione dei prodotti RAE (configurazione Raggruppamenti Rae)
- Come operator si vedono solo i ritiri RAE
- Comparsa del bottone per pdf di ritiro RAE solo se è stato aggiunto un prodotto con flag ritiro RAE

## Gestione ability e permessi
