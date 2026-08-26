"""Fixture per i test end-to-end basati su Playwright.

Avvia un database di test isolato e il backend Flask reale come sottoprocesso,
poi espone una Page Playwright già autenticata come admin (`pw_page`).
Il frontend viene servito esternamente (dalla CI o localmente) e raggiunto
tramite E2E_FRONTEND_URL.
"""

import json as _json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

import database_api
import pytest
from alembic import command
from alembic.config import Config
from playwright.sync_api import Page
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

import src.database.schema  # noqa: F401
from src.database.seed import seed_data


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))


def _assert_test_database_url(url: str) -> str:
  parsed = make_url(url)
  db_name = (parsed.database or '').split('/')[-1]
  if not db_name.startswith('test'):
    raise RuntimeError(f'DATABASE_URL must target a test DB. Got database "{db_name}".')
  return url


def _normalize_local_url(url: str) -> str:
  parsed = urlparse(url)
  if parsed.hostname != 'localhost':
    return url.rstrip('/')

  port = f':{parsed.port}' if parsed.port else ''
  netloc = f'127.0.0.1{port}'
  return urlunparse(parsed._replace(netloc=netloc)).rstrip('/')


def _stamp_database_head() -> None:
  command.stamp(Config(str(PROJECT_ROOT / 'alembic.ini')), 'head')


@pytest.fixture(scope='session')
def database_engine():
  database_url = os.environ.get('DATABASE_URL')
  if not database_url:
    raise RuntimeError('DATABASE_URL is required for e2e tests.')

  safe_url = _assert_test_database_url(database_url)
  engine = create_engine(safe_url, pool_pre_ping=True)
  try:
    with engine.connect():
      pass
  except OperationalError as exc:
    parsed = make_url(safe_url)
    if parsed.drivername.startswith('postgresql') and 'does not exist' in str(exc):
      admin_url = parsed.set(database='postgres')
      admin_engine = create_engine(admin_url, isolation_level='AUTOCOMMIT', pool_pre_ping=True)
      with admin_engine.connect() as conn:
        exists = conn.execute(
          text('SELECT 1 FROM pg_database WHERE datname = :db_name'),
          {'db_name': parsed.database},
        ).scalar()
        if not exists:
          conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
      admin_engine.dispose()
      with engine.connect():
        pass
    else:
      raise
  database_api.Base.metadata.drop_all(bind=engine)
  database_api.Base.metadata.create_all(bind=engine)
  database_api.engine = engine
  seed_data()
  _stamp_database_head()
  yield engine
  engine.dispose()


def _wait_backend_ready(backend_url: str, timeout_seconds: int):
  deadline = time.time() + timeout_seconds
  health_url = f'{backend_url}/'
  while time.time() < deadline:
    try:
      with urlopen(health_url, timeout=2) as response:
        # Non basta "qualcosa ha risposto": un processo estraneo gia' in ascolto
        # sulla porta risponderebbe 404 e i test partirebbero contro di lui,
        # fallendo poi in modo incomprensibile. Si pretende la risposta del
        # nostro indice.
        if response.status == 200 and b'Hello World' in response.read():
          return
    except HTTPError:
      pass
    except URLError:
      pass
    time.sleep(0.5)
  raise RuntimeError(f'Backend did not become ready at {health_url} within {timeout_seconds} seconds.')


@pytest.fixture(scope='session')
def frontend_url() -> str:
  return os.environ.get('E2E_FRONTEND_URL', 'http://localhost:3000/').rstrip('/') + '/'


@pytest.fixture(scope='session')
def backend_url() -> str:
  return _normalize_local_url(os.environ.get('E2E_BACKEND_URL', 'http://127.0.0.1:8080/'))


@pytest.fixture(scope='session')
def backend_server(backend_url: str, database_engine):
  parsed = urlparse(backend_url)
  if parsed.scheme != 'http' or not parsed.hostname:
    pytest.fail(f'E2E_BACKEND_URL must be a plain http URL without path. Got: {backend_url}')
  if parsed.path not in {'', '/'}:
    pytest.fail(f'E2E_BACKEND_URL must not include a path. Got: {backend_url}')

  env = os.environ.copy()
  existing_pythonpath = env.get('PYTHONPATH')
  env['PYTHONPATH'] = f'{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}' if existing_pythonpath else str(PROJECT_ROOT)
  env['LOCAL_PORT'] = str(parsed.port or 8080)
  env.setdefault('IS_DEV', '1')
  env.setdefault('DECODE_JWT_TOKEN', 'dummy')
  # API_PREFIX potrebbe essere impostato a livello di CI per la produzione:
  # va rimosso per il server di test così le route restano ai path semplici.
  env.pop('API_PREFIX', None)

  command_args = [
    sys.executable,
    '-c',
    (
      'import os; from src.__main__ import app; '
      'app.run(host=os.environ.get("E2E_BACKEND_HOST", "127.0.0.1"), '
      'port=int(os.environ["LOCAL_PORT"]), debug=False, use_reloader=False)'
    ),
  ]

  process = subprocess.Popen(
    command_args, cwd=str(PROJECT_ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
  )

  startup_timeout = int(os.environ.get('E2E_BACKEND_STARTUP_TIMEOUT', '20'))
  try:
    _wait_backend_ready(backend_url, startup_timeout)
  except Exception as exc:
    process.terminate()
    stdout, stderr = _drain(process)
    pytest.fail(f'Failed to start backend at {backend_url}: {exc}\nstdout:\n{stdout}\nstderr:\n{stderr}')

  _verify_login(backend_url, process)

  yield backend_url

  process.terminate()
  stdout, stderr = _drain(process)
  Path('backend_stdout.log').write_text(stdout or '')
  Path('backend_stderr.log').write_text(stderr or '')


def _drain(process):
  try:
    return process.communicate(timeout=10)
  except subprocess.TimeoutExpired:
    process.kill()
    return process.communicate()


def _verify_login(backend_url: str, process):
  """Verifica che /user/login funzioni prima di eseguire i test browser."""
  # La password viaggia in chiaro dentro HTTPS: e' il backend a hasharla. La
  # fixture la cifrava, ereditando dal vecchio schema, e il login falliva prima
  # ancora di aprire la pagina autenticata.
  payload = _json.dumps({'email': 'admin', 'password': '1234admin'}).encode('utf-8')
  request = urllib.request.Request(
    f'{backend_url}/user/login', data=payload, headers={'Content-Type': 'application/json'}, method='POST'
  )
  try:
    with urlopen(request, timeout=10) as resp:
      login_data = _json.loads(resp.read())
  except HTTPError as exc:
    login_data = _json.loads(exc.read())
  except URLError as exc:
    process.terminate()
    stdout, stderr = _drain(process)
    pytest.fail(f'Login endpoint not reachable: {exc}\nstdout:\n{stdout}\nstderr:\n{stderr}')

  if login_data.get('status') != 'ok':
    process.terminate()
    stdout, stderr = _drain(process)
    pytest.fail(f'Backend login not working (expected status=ok): {login_data}\nstdout:\n{stdout}\nstderr:\n{stderr}')


@pytest.fixture(scope='session')
def e2e_user(backend_server: str) -> dict:
  return {'email': 'admin', 'password': '1234admin'}


@pytest.fixture(scope='session')
def pw_base_url(frontend_url: str) -> str:
  return frontend_url.rstrip('/')


@pytest.fixture(scope='session')
def warm_frontend(browser, pw_base_url: str, backend_server: str):
  """Scalda il frontend prima che parta il primo test.

  Servito da `vite dev`, il primo accesso fa scoprire a Vite dipendenze non
  ancora ottimizzate (i gruppi di Vuetify sono tanti) e la pagina viene
  ricaricata a metà interazione: il login si perde e il test fallisce in
  timeout per un motivo che non c'entra con cio' che verifica. Un giro a vuoto
  paga l'ottimizzazione una volta sola.

  Per una esecuzione davvero stabile conviene comunque puntare E2E_FRONTEND_URL
  a un bundle servito (`vite preview` o `npm run serve` dopo la build), dove il
  problema non si pone: la CI fa gia' cosi'.
  """
  context = browser.new_context()
  page = context.new_page()
  try:
    for route in ('/', '/dashboard', '/orders'):
      page.goto(f'{pw_base_url}{route}')
      page.wait_for_load_state('networkidle')
  finally:
    context.close()


@pytest.fixture
def pw_page(page: Page, pw_base_url: str, e2e_user: dict, backend_server: str, warm_frontend) -> Page:
  """Page Playwright già autenticata come admin sulla dashboard."""
  page.goto(f'{pw_base_url}/')
  page.wait_for_load_state('networkidle')

  # I locator si risolvono dopo l'attesa: se Vite ha ricaricato durante il
  # caricamento, quelli presi prima punterebbero a nodi non piu' attaccati.
  page.locator("input[type='email'], input[name='email']").fill(e2e_user['email'])
  password = page.locator("input[type='password'], input[name='password']")
  password.fill(e2e_user['password'])
  password.press('Enter')

  page.wait_for_url('**/dashboard', timeout=30_000)
  return page
