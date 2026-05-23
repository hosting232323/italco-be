## Terminologia usata nel documento

- `customer`: il punto vendita / cliente per cui vengono creati gli ordini.
- `admin`: utente con accesso completo a configurazioni e pagine amministrative.
- `operator`: utente operativo con visibilità intermedia.
- `delivery`: utente che entra in gioco dopo la pianificazione giornaliera.
- `RAE`: logica speciale per prodotti/ritiri RAE.
- `Borderò`: pianificazione giornaliera di uno o più ordini assegnati a delivery user, mezzo e data.

Nota: il walkthrough si ferma sostanzialmente all'inizio del ciclo di vita ordine; il mondo `delivery` viene solo introdotto tramite il Borderò.

---

## Vista d'insieme del ciclo mostrato

1. Login customer e verifica del contesto.
2. Creazione ordine lato customer.
3. Configurazione amministrativa necessaria per sbloccare servizi e date.
4. Differenze di comportamento tra customer, admin e operator.
5. Gestione flussi speciali RAE.
6. Passaggio di stato dell'ordine da `acquisito` a `booked`.
7. Inserimento degli ordini nel Borderò.

---

## Elenco sintetico dei flussi

| ID  | Nome flusso                                                 | Attori principali         |
| :-- | :---------------------------------------------------------- | :------------------------ |
| F01 | Accesso customer e contesto iniziale                        | Customer                  |
| F02 | Visibilità del punto di ritiro                              | Customer                  |
| F03 | Creazione ordine come customer                              | Customer                  |
| F04 | Creazione ordine come admin/operator per un customer        | Admin, Operator           |
| F05 | Configurazione servizi                                      | Admin                     |
| F06 | Associazione servizi agli utenti                            | Admin                     |
| F07 | Configurazione aree geografiche                             | Admin                     |
| F08 | Configurazione regole punti vendita/customer                | Admin                     |
| F09 | Calcolo delle date disponibili per il customer              | Customer, Admin           |
| F10 | Differenze dashboard, filtri, azioni e navigation per ruolo | Customer, Admin, Operator |
| F11 | Restrizioni del customer rispetto ad admin/operator         | Customer                  |
| F12 | Creazione ordine con prodotti RAE                           | Admin, Operator           |
| F13 | Visibilità pagine RAE per ruolo                             | Admin, Operator           |
| F14 | Export/PDF degli ordini RAE                                 | Admin, Operator           |
| F15 | Transizione di stato ordine: acquisito -> booked            | Admin, Operator           |
| F16 | Creazione Borderò / pianificazione giornaliera              | Admin, Operator           |
| F17 | Flussi secondari di contesto: GDO, utenti, log              | Admin, Operator           |

---

## Flussi dettagliati

### F01 - Accesso customer e contesto iniziale

- Attore: `customer`
- Obiettivo: entrare in dashboard e verificare che l'utente possa iniziare la creazione ordine.
- Precondizioni:
  - utente customer esistente;
  - seed coerente con customer atteso.
- Passi principali:
  1. login come customer;
  2. apertura dashboard;
  3. verifica del contesto minimo disponibile.
- Risultato atteso:
  - il customer vede la propria dashboard e i propri dati di contesto;
  - non vede opzioni amministrative o operative non pertinenti.

### F02 - Visibilità del punto di ritiro

- Attore: `customer`
- Obiettivo: verificare che il punto di ritiro compaia solo dove previsto.
- Precondizioni:
  - esiste almeno un collection point coerente con i dati seed;
  - il customer ha visibilità sul servizio/tipo d'ordine che lo richiede.
- Passi principali:
  1. aprire creazione ordine;
  2. selezionare il tipo di ordine rilevante;
  3. verificare la presenza del punto di ritiro corretto.
- Risultato atteso:
  - il punto di ritiro è visibile solo nel contesto giusto;
  - etichetta e nome sono coerenti con la configurazione.

### F03 - Creazione ordine come customer

- Attore: `customer`
- Obiettivo: creare un ordine dalla dashboard customer.
- Precondizioni:
  - servizi configurati;
  - area geografica configurata;
  - regole minime tali da rendere disponibili alcune date.
- Passi principali:
  1. apertura popup/modale di creazione ordine;
  2. selezione tipo ordine;
  3. selezione servizio tra quelli disponibili;
  4. compilazione prodotto, destinatario, indirizzo, recapito, contrassegno e altri campi richiesti;
  5. selezione data prevista dal cliente tra quelle disponibili;
  6. conferma creazione.
- Risultato atteso:
  - l'ordine viene creato con i vincoli customer applicati;
  - il customer non può aggirare i limiti su servizi, date e campi non concessi.

### F04 - Creazione ordine come admin/operator per un customer

- Attori: `admin`, `operator`
- Obiettivo: creare un ordine per conto di un customer.
- Precondizioni:
  - esiste almeno un customer selezionabile;
  - i servizi necessari sono configurati.
- Passi principali:
  1. aprire creazione ordine da admin/operator;
  2. selezionare il customer target;
  3. selezionare tipo e servizio;
  4. compilare i campi dell'ordine;
  5. impostare date e dati aggiuntivi disponibili per il ruolo.
- Risultato atteso:
  - admin/operator vedono uno step in più rispetto al customer: la selezione del customer;
  - il flusso di creazione non è identico a quello del customer.

### F05 - Configurazione servizi

- Attore: `admin`
- Obiettivo: configurare i servizi che impattano la creazione ordine.
- Aspetti emersi:
  - ogni servizio ha un `tipo`;
  - il tipo influisce su come il servizio appare nel form ordine;
  - non basta il tipo: servono anche abilitazioni/etichette coerenti con gli utenti.
- Risultato atteso:
  - i servizi disponibili in fase di ordine dipendono dalla configurazione amministrativa.

### F06 - Associazione servizi agli utenti

- Attore: `admin`
- Obiettivo: associare i servizi ai singoli customer e governarne la visibilità.
- Aspetti emersi:
  - l'associazione è per singolo utente, non per gruppi di servizi;
  - un customer vede solo i servizi a lui associati/abilitati;
  - il walkthrough ha evidenziato anche un bug/regression risk: il backend consente associazioni a utenti non customer, cosa che non dovrebbe essere possibile.
- Risultato atteso:
  - la UI e il BE convergono nel consentire associazioni valide solo verso utenti customer;
  - il customer vede esclusivamente i servizi previsti per lui.

### F07 - Configurazione aree geografiche

- Attore: `admin`
- Obiettivo: definire province/aree geografiche per sbloccare la possibilità di ordinare.
- Aspetti emersi:
  - senza regole per l'area geografica il customer non dovrebbe poter effettuare ordini;
  - le aree geografiche sono la base delle disponibilità sul calendario.
- Risultato atteso:
  - il customer può ordinare solo nelle aree abilitate dalla configurazione.

### F08 - Configurazione regole punti vendita/customer

- Attore: `admin`
- Obiettivo: aggiungere vincoli più specifici sul singolo punto vendita/customer.
- Aspetti emersi:
  - sopra ci sono le regole geografiche di base;
  - sotto possono esserci regole aggiuntive o più restrittive sul customer specifico;
  - queste regole possono combinarsi con i vincoli di area.
- Risultato atteso:
  - la disponibilità effettiva per il customer è il risultato della combinazione tra regole generali e regole specifiche.

### F09 - Calcolo delle date disponibili per il customer

- Attori: `customer`, `admin`
- Obiettivo: determinare la `data prevista dal cliente` mostrata nel calendario customer.
- Vincoli esplicitati nel walkthrough:
  1. vincoli dell'area geografica;
  2. vincoli del singolo punto vendita/customer;
  3. `max giornalieri` del servizio.
- Risultato atteso:
  - il customer vede solo le date consentite da questi tre livelli di regole;
  - la disponibilità del calendario è una sintesi di business rules, non una semplice scelta libera.

### F10 - Differenze dashboard, filtri, azioni e navigation per ruolo

- Attori: `customer`, `admin`, `operator`
- Obiettivo: verificare che UI e permessi cambino in base al ruolo.
- Aspetti emersi:
  - filtri diversi tra customer, admin e operator;
  - azioni diverse sulla dashboard ordini;
  - voci del navigation drawer diverse;
  - pagine visibili diverse tra ruoli.
- Risultato atteso:
  - ogni ruolo vede solo ciò che gli compete;
  - i componenti di navigazione riflettono i permessi reali.

### F11 - Restrizioni del customer rispetto ad admin/operator

- Attore: `customer`
- Obiettivo: garantire che il customer non abbia accesso a opzioni di scheduling/operatività interna.
- Aspetti emersi:
  - il customer non vede la data di consegna;
  - il customer non dovrebbe vedere selector/tab/form collegati al delivery;
  - il customer non può aggiungere prodotti con flag `ritiro RAE`.
- Risultato atteso:
  - i vincoli customer sono sia funzionali sia di visibilità frontend.

### F12 - Creazione ordine con prodotti RAE

- Attori: `admin`, `operator` (a seconda del punto esatto del flusso), non `customer`
- Obiettivo: inserire prodotti RAE in ordine.
- Aspetti emersi:
  - il prodotto RAE non è una semplice stringa libera come il prodotto standard;
  - richiede una quantità;
  - il frontend deve segnalare chiaramente che il prodotto è RAE.
- Risultato atteso:
  - un ordine con prodotto RAE è riconoscibile e segue logiche diverse da un ordine standard.

### F13 - Visibilità pagine RAE per ruolo

- Attori: `admin`, `operator`
- Obiettivo: distinguere dashboard RAE e configurazione RAE.
- Aspetti emersi:
  - operator vede la dashboard/lista ritiri RAE;
  - admin vede sia la dashboard RAE sia la configurazione/raggruppamenti RAE.
- Risultato atteso:
  - i permessi RAE seguono una separazione chiara tra consultazione operativa e configurazione amministrativa.

### F14 - Export/PDF degli ordini RAE

- Attori: `admin`, `operator`
- Obiettivo: esporre un'azione aggiuntiva per gli ordini che contengono prodotti RAE.
- Aspetti emersi:
  - compare un bottone dedicato solo sugli ordini RAE;
  - il bottone dovrebbe portare a un PDF/export corretto.
- Risultato atteso:
  - gli ordini non RAE non espongono tale azione;
  - gli ordini RAE sì.

### F15 - Transizione di stato ordine: acquisito -> booked

- Attori: `admin`, `operator`
- Obiettivo: portare un ordine in stato `booked` impostando la data di consegna.
- Aspetti emersi:
  - un ordine creato senza data di consegna resta `acquisito`;
  - aggiungendo la data di consegna diventa `booked`.
- Risultato atteso:
  - la presenza/assenza della data di consegna impatta direttamente lo stato ordine.

### F16 - Creazione Borderò / pianificazione giornaliera

- Attori: `admin`, `operator`
- Obiettivo: raggruppare ordini `booked` in una pianificazione giornaliera.
- Passi principali:
  1. selezionare ordini eleggibili;
  2. assegnare delivery user;
  3. assegnare mezzo;
  4. assegnare data;
  5. creare il Borderò.
- Aspetti emersi:
  - il Borderò è il gruppo di ordini che un delivery user dovrà eseguire in una giornata;
  - da qui in poi entra il mondo delivery.
- Risultato atteso:
  - solo ordini nello stato corretto possono essere inclusi;
  - la creazione produce una pianificazione coerente.

### F17 - Flussi secondari di contesto: GDO, utenti, log

- Attori: `admin`, in parte `operator`
- Obiettivo: registrare le pagine viste che non appartengono al flusso core ordine ma che impattano permessi e contesto.
- Aspetti emersi:
  - pagina GDO / raggruppamenti utenti;
  - pagina utenti e configurazione utenti;
  - pagina log con richieste verso il backend.
- Risultato atteso:
  - queste pagine seguono permessi specifici e meritano almeno test di visibilità/accesso.

---

## Vincoli di business più importanti emersi

I punti più critici per i test sono questi:

1. il customer vede solo servizi associati e consentiti;
2. il customer può ordinare solo se esistono configurazioni geografiche coerenti;
3. la data prevista dal cliente dipende da tre livelli di vincolo;
4. admin/operator hanno campi, permessi e scheduling diversi dal customer;
5. il mondo RAE introduce un ramo logico separato;
6. la transizione `acquisito -> booked -> Borderò` segna l'inizio del lifecycle operativo dell'ordine.

---

## Stato attuale unit test collegati a questa guida

Nota: il dettaglio scenario-per-scenario con stato `[x]` / `[ ]` vive in `docs/flussi-ordine-test-matrix.md`.

- [x] `TM-04` / `F06`: il customer vede solo i servizi a lui associati.
- [x] `RG-01` / `F06`: il backend rifiuta associazioni servizio -> utente non customer.
- [x] `TM-06` / `F08`: la disponibilità del customer riflette il vincolo customer-specific.
- [x] `TM-08` / `F15`: un ordine `acquisito` passa a `booked` quando viene impostata la `booking_date`.
- [ ] Tutti gli altri scenari della matrice sono ancora da implementare lato unit test.

---

## Fuori perimetro del walkthrough

I seguenti aspetti sono solo introdotti o citati, ma non realmente spiegati fino in fondo nel walkthrough:

- lifecycle completo del delivery user;
- esecuzione consegna sul campo;
- stati successivi al Borderò;
- eventuali processi di esportazione/importazione oltre ai casi mostrati;
- semantica completa di tutte le pagine amministrative secondarie.

Questi punti meritano documentazione separata quando verranno spiegati in una sessione successiva.
