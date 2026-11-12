# Conservazione dei dati personali

Durate scelte per la privacy (`/privacy` di italco-fe). Sono scelte prudenti,
non obblighi di legge: si possono cambiare con le variabili d'ambiente sotto.

| Dato | Durata | Come viene rispettata |
|---|---|---|
| Ultima posizione del corriere (`delivery_user_info.lat/lon`) | fine giornata, comunque 24 ore | azzerata quando si chiude il borderò; `retention_cleanup` azzera quelle non aggiornate da `RETENTION_POSITION_HOURS` |
| Eventi di posizione (`schedule_item_user`: chi ha attivato/chiuso e quando) | 365 giorni | `retention_cleanup` |
| Richieste demo salvate (`mail`) | 365 giorni | `retention_cleanup` |
| Log di audit (`static/<prod\|test>/logs/AAAA-MM/AAAA-MM-GG.jsonl` e `.idx`) | 90 giorni | `retention_cleanup` |
| Foto di consegna (`photo` e file in `photos/`) | 24 mesi dalla chiusura dell'ordine | `retention_cleanup` (file e riga, tramite `SessionWithStorage`) |
| Firma di consegna (`order.signature`) | 24 mesi dalla chiusura dell'ordine | `retention_cleanup` (azzera il campo, l'ordine resta) |
| Rapporti di errore dell'app (log del servizio) | 30 giorni | **a mano**: rotazione dei log Docker (sotto) |
| Avvisi Telegram | 1 mese | **a mano**: timer della chat (sotto) |

I dati degli ordini, i documenti RAEE (DTR/FIR) e le altre tabelle **non** sono
toccati da questo lavoro: le durate vanno ancora decise con il cliente.

Le durate valgono sul sistema attivo. I **backup** (database e cartella dei file,
server separato, `BACKUP_DAYS` = 20) conservano ancora i dati cancellati: spariscono
dalle copie entro altri 20 giorni.

## Ultima posizione a fine giornata

Il backend tiene una sola posizione per corriere, sovrascritta a ogni invio
(`POST /user/position`). Quando l'ultimo elemento del borderò è completato la
posizione condivisa si chiude (`close_schedule_position_if_done`) e da lì la
posizione del corriere che la teneva viene azzerata.

Se il corriere non completa il borderò (non esiste un comando "Finisci giornata")
la posizione resta fino al passaggio di `retention_cleanup`, che azzera quelle non
aggiornate da `RETENTION_POSITION_HOURS` ore. La scadenza si basa su `updated_at`,
che cambia a ogni salvataggio della scheda (posizione ma anche altre modifiche).

Un invio di posizione arrivato dopo la chiusura la riscrive: viene azzerata di
nuovo dal job successivo.

## Variabili d'ambiente

Nell'`env_file` del servizio (stesso posto delle altre). Vuota o non numerica =
default; `0` o negativo disattiva quella pulizia.

| Variabile | Default | Cosa pulisce |
|---|---|---|
| `RETENTION_POSITION_HOURS` | `24` | ultima posizione dei corrieri (ore) |
| `RETENTION_POSITION_EVENTS_DAYS` | `365` | eventi di attivazione/chiusura della posizione |
| `RETENTION_DEMO_REQUEST_DAYS` | `365` | richieste demo in archivio (tabella `mail`) |
| `RETENTION_LOG_DAYS` | `90` | log di audit |
| `RETENTION_DELIVERY_PROOF_MONTHS` | `24` | foto e firma di consegna (mesi) |

Degli eventi di posizione resta sempre l'ultimo di un borderò ancora aperto,
perché dice chi tiene la posizione. Se l'ultimo è una chiusura si cancella tutto.

## Foto e firma di consegna (24 mesi)

Si applicano solo a ordini **chiusi**: stato `DELIVERED` o `NOT_DELIVERED`. Le foto e la
firma di un ordine ancora aperto (in consegna, da riprogrammare, pianificato) non si
toccano mai, qualunque sia la data.

- **Data di riferimento**: `completion_date` dell'ordine (la imposta il backend alla
  chiusura). Se manca, per le **foto** si usa la data in cui la foto è stata caricata
  (`photo.created_at`, la foto nasce alla chiusura della consegna); per la **firma**
  l'ultima modifica dell'ordine (`updated_at`, sempre successiva alla chiusura: nel
  dubbio la firma resta di più, mai di meno).
- **Foto**: si cancellano file e riga del database passando da `SessionWithStorage`, come
  `delete_order`: il file sparisce solo dopo il commit del database, un file già
  mancante non è un errore, e si lavora a lotti da 500 per non tenere una transazione
  enorme.
- **Firma**: vive solo in `order.signature` (un unico campo binario, l'immagine disegnata
  sullo schermo). Si azzera (`NULL`) senza cancellare l'ordine. I PDF del singolo ordine
  e del borderò (`get_signature_slots`) e le esportazioni già gestiscono la firma assente
  (riquadro vuoto); il tracciamento pubblico non la espone.
- Con `RETENTION_DELIVERY_PROOF_MONTHS=0` (o negativo) foto e firma restano per sempre.

## Il job

```bash
# sul server, nel container del backend: prima solo conteggio
docker exec <container-backend> python -m scripts.retention_cleanup --dry-run
# poi cancella
docker exec <container-backend> python -m scripts.retention_cleanup
```

Cron giornaliero (ogni notte alle 03:30), sul server:

```cron
30 3 * * * docker exec <container-backend> python -m scripts.retention_cleanup >> /var/log/retention_cleanup.log 2>&1
```

Il comando stampa per ogni voce quanti record/file ha cancellato (o cancellerebbe
con `--dry-run`).

## Da fare a mano (non coperto dal job)

- **Rapporti di errore (30 giorni).** Finiscono nel log del servizio. Limita la
  rotazione dei log Docker del container backend (`docker-compose.yml` o
  `daemon.json`): per esempio `max-size: "10m"` e `max-file: "3"`; per un limite
  a tempo con journald, `MaxRetentionSec=30day` in `journald.conf`.
- **Telegram (1 mese).** Nella chat o nel gruppo che riceve gli avvisi:
  impostazioni della chat, *Cancellazione automatica messaggi*, 1 mese.
