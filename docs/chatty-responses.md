# Chatty: migrazione a Responses

L'Assistants API è stata dismessa il 26 agosto 2026. La creazione di thread
in `POST /chatty/chat` utilizzava quell'API e restituiva 404.

Fonte: https://developers.openai.com/api/docs/assistants/migration

## Configurazione e rilascio

- Ricostruire e distribuire l'immagine backend, così viene installato
  `openai>=2.41.1,<3` da `pyproject.toml`.
- Conservare `OPENAI_KEY` della stessa organizzazione OpenAI.
- `OPENAI_MODEL` è opzionale: il default è `gpt-4.1-mini`.
  Verificare che il progetto OpenAI abbia accesso al modello scelto.
- `CHATTY_INSTRUCTIONS` permette di riportare eventuali istruzioni personalizzate
  del vecchio Assistant. Quelle remote non sono presenti nel repository:
  il default locale è un assistente in italiano che consulta gli ordini.
- `ASSISTANT_ID` non viene più letto.
- Se il comando Gunicorn viene sovrascritto dal deploy, impostare un timeout
  adeguato al ciclo di tool (il Dockerfile usa 180 secondi).

Non servono migrazioni SQL. La colonna `Chatty.thread_id` contiene ora un ID
`conv_...`. Il frontend mantiene lo stesso contratto:
`{status, session_id, response}`.

## Sessioni e ricerca

Le nuove chat usano Conversations e Responses. Le sessioni `thread_...` oppure
le conversazioni eliminate vengono sostituite al messaggio successivo da una nuova
conversazione. La cronologia dei vecchi thread non viene recuperata; la sua lettura
restituisce 410. La cronologia corrente mantiene l'ordine dal messaggio più recente.

Ogni nuova conversazione è associata nei metadata a utente, azienda attiva e ruolo.
Sia invio sia lettura richiedono autenticazione e verificano questa associazione.
Una sessione di un altro utente/azienda/ruolo restituisce 403.

Il tool cerca per ID ordine/consegna, senza richiedere una data, oppure per date
di creazione. Conserva il filtro aziendale e cliente e limita gli autisti alle
assegnazioni. Richieste senza criteri validi non interrogano tutti gli ordini.

Il ciclo di tool è limitato; timeout ed errori OpenAI restituiscono un errore
controllato senza esporre la risposta upstream. Il servizio non usa polling
Assistants. Le richieste OpenAI hanno timeout di 20 secondi e retry disattivati.

## Verifica

`python -m pytest tests/unit/end_points/test_chatty.py -q`

La suite usa il database dedicato in `.env.test`. OpenAI è simulato; un test
usa l'SDK reale con trasporto HTTP simulato per verificare serializzazione,
risultati dei tool e paginazione della cronologia, senza consumare credito.

Dopo il rilascio verificare una nuova chat, una domanda per ID e un secondo
messaggio nella stessa sessione. Il saldo e l'accesso effettivo al modello
richiedono una verifica sull'organizzazione OpenAI di produzione.
