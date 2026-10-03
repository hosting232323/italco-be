import os
import tempfile
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_ENV_FILE = PROJECT_ROOT / '.env.test'

if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

if not TEST_ENV_FILE.is_file():
  raise RuntimeError(f'Missing pytest env file: {TEST_ENV_FILE}')

load_dotenv(TEST_ENV_FILE, override=True)

# Deve avvenire qui, prima di qualunque `import src`: src/__init__.py legge
# STATIC_FOLDER a import-time e lo congela nel modulo. Se tests/e2e/conftest.py
# importa src.database.schema prima che questo setdefault sia passato (capita
# quando la sessione raccoglie anche tests/e2e insieme a tests/unit),
# STATIC_FOLDER resta quello reale del progetto: i test che si aspettano una
# cartella vuota trovano invece file veri lasciati da run precedenti.
os.environ.setdefault('STATIC_FOLDER', tempfile.mkdtemp(prefix='italco-test-static-'))

# Le soglie configurate per l'ambiente non devono bloccare le richieste dei
# test API. I test specifici delle soglie modificano direttamente i valori
# dell'app con monkeypatch.
os.environ['DELIVERY_APP_MIN_BUILD_NUMBER_IOS'] = ''
os.environ['DELIVERY_APP_MIN_BUILD_NUMBER_ANDROID'] = ''
os.environ['DELIVERY_APP_MIN_BUILD_NUMBER'] = ''
