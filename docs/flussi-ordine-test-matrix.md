## Legenda

- `P0`: copertura minima indispensabile.
- `P1`: copertura importante ma secondaria rispetto al core ordine.
- `P2`: copertura utile come regressione o hardening.

- `E2E`: test end-to-end orientato alla UI.
- `INT`: test integration API/BE.
- `REG`: regression test mirato su bug noto.
- `Stato unit test`: `[x]` scenario coperto oggi da unit test backend, `[ ]` scenario non ancora coperto da unit test backend.

---

## Scenari P0 - core business

| Stato unit test | ID    | Flusso                              | Livello   | Attore         | Precondizioni                                             | Scenario                                                          | Assert principali                                                                                      |
| :--------------- | :---- | :---------------------------------- | :-------- | :------------- | :-------------------------------------------------------- | :---------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------- |
| [ ] | TM-01 | F02 Visibilità punto di ritiro      | E2E       | Customer       | esiste almeno un collection point valido                  | aprire creazione ordine e selezionare il tipo corretto            | il punto di ritiro compare solo nel contesto previsto e con il nome atteso                             |
| [ ] | TM-02 | F03 Creazione ordine customer       | E2E       | Customer       | servizi, area geografica e date configurate               | creare un ordine completo come customer                           | ordine creato; servizio selezionabile; data prevista disponibile; nessun campo non consentito visibile |
| [ ] | TM-03 | F04 Creazione ordine admin/operator | E2E       | Admin/Operator | esiste almeno un customer                                 | creare ordine per conto di un customer                            | compare step di selezione customer; ordine creato correttamente                                        |
| [x] | TM-04 | F06 Servizi per utente              | E2E + INT | Admin/Customer | servizio associato solo a un customer target              | associare servizio e poi fare login come customer                 | il customer vede solo i servizi a lui associati                                                        |
| [ ] | TM-05 | F07 Aree geografiche                | E2E + INT | Admin/Customer | customer senza configurazione geografica iniziale         | creare area/regola geografica e tornare al flusso ordine customer | prima non ci sono date/ordine bloccato; dopo la configurazione il customer può procedere               |
| [x] | TM-06 | F08 Regole customer specifiche      | E2E + INT | Admin/Customer | area geografica configurata, customer con regola dedicata | applicare regola customer-specific e aprire calendario ordine     | la disponibilità del customer riflette anche la regola specifica, non solo quella geografica           |
| [ ] | TM-07 | F09 Max giornalieri servizio        | E2E + INT | Admin/Customer | servizio con limite giornaliero noto                      | saturare il massimo giornaliero del servizio su una certa data    | la data non è più selezionabile per nuovi ordini customer con quel servizio                            |
| [x] | TM-08 | F15 Stato acquisito/booked          | E2E + INT | Admin/Operator | ordine esistente                                          | creare o modificare ordine senza data consegna, poi aggiungerla   | senza data consegna stato `acquisito`; con data consegna stato `booked`                                |
| [ ] | TM-09 | F16 Creazione Borderò               | E2E + INT | Admin/Operator | ordini `booked`, delivery user, mezzo e data disponibili  | creare un Borderò con uno o più ordini                            | il Borderò viene creato; gli ordini entrano nella pianificazione giornaliera                           |
| [ ] | TM-10 | F16 Eleggibilità Borderò            | E2E + INT | Admin/Operator | ordine `acquisito` e ordine `booked`                      | tentare di inserire entrambi nel Borderò                          | gli ordini non `booked` non sono eleggibili o generano errore coerente                                 |

---

## Scenari P1 - permessi, visibilità e ruoli

| Stato unit test | ID    | Flusso                                  | Livello | Attore                  | Precondizioni                         | Scenario                                           | Assert principali                                                                 |
| :--------------- | :---- | :-------------------------------------- | :------ | :---------------------- | :------------------------------------ | :------------------------------------------------- | :-------------------------------------------------------------------------------- |
| [ ] | TM-11 | F10 Navigation per ruolo                | E2E     | Customer/Admin/Operator | utenti dei tre ruoli disponibili      | confrontare drawer e pagine accessibili            | ogni ruolo vede solo voci e pagine coerenti con i permessi                        |
| [ ] | TM-12 | F10 Filtri e azioni dashboard per ruolo | E2E     | Customer/Admin/Operator | ordini presenti in dashboard          | aprire dashboard e confrontare filtri/azioni       | customer, admin e operator mostrano filtri e azioni diversi come da dominio       |
| [ ] | TM-13 | F11 Restrizioni customer                | E2E     | Customer                | login customer                        | aprire creazione ordine customer                   | il customer non vede data consegna, campi delivery o opzioni interne              |
| [ ] | TM-14 | F12 Creazione ordine RAE                | E2E     | Admin/Operator          | configurazione RAE minima disponibile | creare ordine con prodotto RAE                     | il prodotto RAE richiede quantità, viene marcato come RAE e l'ordine viene creato |
| [ ] | TM-15 | F13 Permessi pagine RAE                 | E2E     | Admin/Operator          | login admin e operator                | aprire pagine RAE                                  | operator vede dashboard/lista RAE; admin vede anche configurazione/raggruppamenti |
| [ ] | TM-16 | F14 Export RAE                          | E2E     | Admin/Operator          | esiste un ordine con prodotto RAE     | aprire dashboard ordini e usare l'azione di export | sugli ordini RAE compare il bottone dedicato; sugli ordini non RAE no             |
| [ ] | TM-17 | F17 Pagina log                          | E2E     | Admin                   | login admin                           | aprire pagina log                                  | la pagina è accessibile e mostra il contesto richiesto dal ruolo                  |
| [ ] | TM-18 | F17 Pagine utenti/GDO                   | E2E     | Admin                   | login admin                           | aprire pagine utenti e GDO                         | le pagine sono visibili e coerenti con il ruolo amministrativo                    |

---

## Scenari P2 - regressioni e bug già emersi

| Stato unit test | ID    | Bug / rischio                                                               | Livello         | Attore         | Precondizioni                     | Scenario                                          | Assert principali                                                                   |
| :--------------- | :---- | :-------------------------------------------------------------------------- | :-------------- | :------------- | :-------------------------------- | :------------------------------------------------ | :---------------------------------------------------------------------------------- |
| [x] | RG-01 | Il backend non deve consentire associazioni servizio -> utente non customer | INT + REG       | Admin/API      | utente non customer esistente     | tentare associazione servizio a delivery/operator | richiesta rifiutata o validazione esplicita coerente                                |
| [ ] | RG-02 | Il customer non deve vedere selector/tab delivery                           | E2E + REG       | Customer       | login customer                    | aprire dashboard/creazione ordine                 | nessun form delivery o selector improprio visibile                                  |
| [ ] | RG-03 | I filtri dashboard customer devono aprirsi correttamente                    | E2E + REG       | Customer       | ordini presenti                   | aprire i filtri dalla dashboard customer          | la UI apre i filtri senza errore e il customer può usarli                           |
| [ ] | RG-04 | I campi numerici/prezzo non devono accettare valori negativi                | E2E + INT + REG | Admin          | form con selector numerici/prezzo | inserire numeri negativi o formati invalidi       | il FE blocca o il BE rifiuta; non si salvano valori invalidi                        |
| [ ] | RG-05 | La selezione piano non deve inviare stringa vuota al DB                     | E2E + INT + REG | Admin/Operator | form ordine aperto                | lasciare il piano non selezionato e confermare    | compare un errore utente coerente oppure il submit è disabilitato; niente errore DB |

---

## Copertura minima consigliata per la prima iterazione

Se si vuole partire con una prima ondata di test ad alto valore, la priorità consigliata è:

1. `TM-02` Creazione ordine customer.
2. `TM-04` Servizi visibili solo per il customer corretto.
3. `TM-05` e `TM-06` per i vincoli geografici e customer-specific.
4. `TM-07` per il vincolo `max giornalieri`.
5. `TM-13` per le restrizioni customer.
6. `TM-14` e `TM-16` per il ramo RAE.
7. `TM-08`, `TM-09` e `TM-10` per il passaggio verso Borderò.
8. `RG-01`, `RG-02`, `RG-04`, `RG-05` come regressioni ad alto rischio.

---
