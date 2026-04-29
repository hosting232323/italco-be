## BUG BE: E' possibili assegnare servizi a utenti non customer (non dovrebbe essere possibile)

## BUG FE: Controlli campi selector possono essere negativi (solo positivi a seconda cifra decimale)

## BUG FE: Form Delivery a disposizione per customer (rimuovere il selector dei form se customer)

## BUG FE O BE(?): Da utente customer non è possibile aprire i filtri nella dashboard

## BUG FE: Selezione piano passa stringa vuota se non è stato selezionato nessun piano (invece di mostrare un messaggio di errore o disabilitare il pulsante di conferma) dà errore in db

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
