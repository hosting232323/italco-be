# Conservazione dei dati personali

Durate scelte per la privacy (`/privacy` di italco-fe). Sono scelte prudenti,
non obblighi di legge: si possono cambiare con le variabili d'ambiente sotto.

| Dato | Durata | Come viene rispettata |
|---|---|---|
| Ultima posizione del corriere (`delivery_user_info.lat/lon`) | fine giornata, comunque 24 ore | azzerata quando si chiude il borderò; `retention_cleanup` azzera quelle non aggiornate da `RETENTION_POSITION_HOURS` |
| Eventi di posizione (`schedule_item_user`: chi ha attivato/chiuso e quando) | 365 giorni | `retention_cleanup` |
| Richieste demo salvate (`mail`) | 365 giorni | `retention_cleanup` |
| Log di audit (`static/<prod\|test>/logs/AAAA-MM/AAAA-MM-GG.jsonl` e `.idx`) | 90 giorni | `retention_cleanup` |
| Rapporti di errore dell'app (log del servizio) | 30 giorni | **a mano**: rotazione dei log Docker (sotto) |
| Avvisi Telegram | 1 mese | **a mano**: timer della chat (sotto) |

Foto e firme di consegna, e i dati degli ordini, **non** sono toccati da questo
lavoro: le durate vanno ancora decise con il cliente.

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

Degli eventi di posizione resta sempre l'ultimo di un borderò ancora aperto,
perché dice chi tiene la posizione. Se l'ultimo è una chiusura si cancella tutto.

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
