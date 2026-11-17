# italco-be

```bash
sudo apt update
sudo apt install -y libpq-dev postgresql-client restic pkg-config libcairo2-dev
```

## Install from pyproject

```bash
# install only the package, without the dev dependencies
pip install .

# install the package with the dev dependencies from pyproject.toml
pip install ".[dev]"


# using uv
uv sync

# to include the dev dependencies
uv sync --extra dev
```

## Run the tests

### Tests are automatically set to run with .env.test file environment variables

Run this docker-compose line to set up a test database with .env.test environment variables:

```bash
docker compose --env-file .env.test up -d
```

```bash
# run all tests
pytest

# run only unit tests (exclude e2e tests)
pytest -m "not e2e"

# run only e2e tests
pytest -m e2e ./tests/e2e

# run tests with coverage (stessi comandi della pipeline)
coverage run -m pytest -m "not e2e"
coverage report
```

Note: for running the tests make sure the database name starts with `test` to avoid any accidental data loss. e.g. `test_italco_db`

`--reset` is intentionally guarded and only works when `DATABASE_URL` points to a database whose name starts with `test`.
When `.env.test` exists, `uv run -m seed_data --reset` loads it automatically before connecting.

## Run GitLab CI jobs locally

Use `gitlab-ci-local` to validate pipeline jobs before pushing:

```bash
# list jobs
gitlab-ci-local --list

# validate dependency chain
gitlab-ci-local --validate-dependency-chain

# run main backend checks
gitlab-ci-local lint_backend unit_tests --timestamps

# run e2e pipeline job locally (includes Playwright install)
# prefer local frontend checkout to avoid CI token dependency
gitlab-ci-local e2e_tests --variable LOCAL_ITALCO_FE_DIR=/absolute/path/to/italco-fe --timestamps

# run only Playwright e2e job locally (recommended while migrating from Selenium)
gitlab-ci-local e2e_playwright_tests --variable LOCAL_ITALCO_FE_DIR=/absolute/path/to/italco-fe --timestamps

# if using docker executor and local FE path, mount host path into container 
gitlab-ci-local e2e_playwright_tests --variable LOCAL_ITALCO_FE_DIR=/local-italco-fe --volume "$PWD/../italco-fe:/local-italco-fe" --timestamps

# optional: use a public/private repo URL if no local checkout is available

gitlab-ci-local e2e_tests --variable ITALCO_FE_REPO_URL=https://gitlab.com/generic-lab/italco/italco-fe.git --timestamps
```


## Pagamento automatico (abbonamento Stripe)

Il super admin accende il flag `automatic_payment` e fissa il prezzo mensile per attività; l'admin si abbona dalla pagina di configurazione (Stripe Checkout) e gestisce l'abbonamento dal Customer Portal.

### Variabili d'ambiente

| Variabile | Obbligatoria | Note |
| --- | --- | --- |
| `STRIPE_SECRET_KEY` | sì | chiave segreta (`sk_live_...` in prod, `sk_test_...` altrove). Senza, checkout/portale rispondono con un ko leggibile |
| `STRIPE_WEBHOOK_SECRET` | sì | segreto di firma del webhook (`whsec_...`). Senza, il webhook risponde 503 e non applica nulla |
| `FRONTEND_URL` | sì | base degli URL di ritorno da Checkout/Portale (es. `https://hubstra.it`) |

Su GitLab sono variabili CI/CD (mascherate) passate all'`env_file` da `gitlab/deploy.yml`: vanno definite per ogni ambiente, con chiavi di test per test e chiavi live per produzione.

### Configurazione su Stripe (una volta per ambiente)

1. **Webhook endpoint**: Developers → Webhooks → Add endpoint, URL `https://<host>/api/subscription/webhook`, eventi `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`. Copiare il *Signing secret* in `STRIPE_WEBHOOK_SECRET`.
2. **Customer Portal**: Settings → Billing → Customer portal → attivare il portale e abilitare almeno la disdetta dell'abbonamento e l'aggiornamento del metodo di pagamento. Il prezzo non va reso modificabile dal cliente: lo decide il super admin.
3. Il prodotto `hubstra_subscription` si crea da solo al primo checkout.

Comportamento da sapere:

- Il webhook ignora gli eventi già elaborati (per `event.id`) e quelli più vecchi dell'ultimo stato applicato; company inesistente o dati sporchi → `200` e log, mai `500`.
- Il flag non si spegne finché l'abbonamento addebita (va prima disdetto, anche a fine periodo).
- Il prezzo si cambia da `PUT /subscription/company/<id>/price` o dal form company; con un abbonamento vivo (anche `past_due`) passa sempre prima da Stripe.
- La pagina abbonamento rilegge Stripe solo se lo stato locale ha più di 5 minuti; `POST /subscription/sync` rilegge sempre. Timeout 10 s e 2 retry di rete.
- `/subscription` è escluso dal log dei body (webhook e URL di checkout/portale).


## Backup di produzione (container `<SERVICE>-backup`)

`deploy_prod` (solo lui: `BACKUP_CONTAINER: "1"`) avvia accanto all'API il container `${SERVICE}-backup`, dalla stessa immagine, con gli stessi `env_file`, rete e volumi, senza router Traefik. Il suo comando è `backup.sh`: dorme fino al prossimo orario di `BACKUP_TIMES` e lancia `python -m src.backup` (`src/backup.py`), che fa il dump del database e il backup di `STATIC_FOLDER/prod` verso la macchina di backup (`db_backup` e `folder_backup` di generic-lib, `server=True`) e aspetta che finiscano. Un errore lo segnala generic-lib su Telegram; nel log del container resta una riga per giro.

| Variabile | Default | Note |
| --- | --- | --- |
| `BACKUP_TIMES` | `05:00 11:00 17:00 23:00` | orari `HH:MM` UTC separati da spazi; quelli non validi vengono ignorati |
| `BACKUP_FOLDER` | — | senza, il deploy non avvia il container |

- Il backup gira sotto il lock `/tmp/italco-backup.lock`. Lancio a mano, senza sovrapporsi a quello programmato: `docker exec <SERVICE>-backup flock /tmp/italco-backup.lock python -m src.backup` (sul server di produzione).
- A ogni deploy il job aspetta (al massimo 2 ore) che il lock sia libero prima di ricreare il container.
- Gli endpoint `/internal-backup` e `/folder-backup` restano finché i backup del container non sono verificati: fino ad allora, se cron-job.org li chiama agli stessi orari, i backup sono doppi.
