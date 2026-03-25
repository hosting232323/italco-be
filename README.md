# italco-be

```bash
sudo apt update
sudo apt install -y pkg-config libcairo2-dev cmake
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
pytest ./tests/unit

# run only e2e tests
pytest ./tests/e2e
```

Note: for running the tests make sure the database name starts with `test` to avoid any accidental data loss. e.g. `test_italco_db`

## Seed the database

```bash
# seed only if the configured database is empty
uv run -m seed_data

# recreate and reseed a test database
uv run -m seed_data --reset
```

`--reset` is intentionally guarded and only works when `DATABASE_URL` points to a database whose name starts with `test`.
When `.env.test` exists, `uv run -m seed_data --reset` loads it automatically before connecting.
