# italco-be

```bash
sudo apt update
sudo apt install -y pkg-config libcairo2-dev cmake
pip install -r requirements.txt
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

```bash
# run all tests
pytest

# run only unit tests (exclude e2e tests)
pytest ./tests/unit

# run only e2e tests
pytest ./tests/e2e
```

Note: for running the tests make sure the database name starts with `test` to avoid any accidental data loss. e.g. `test_italco_db`
