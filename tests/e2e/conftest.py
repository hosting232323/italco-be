import json as _json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

from alembic import command
from alembic.config import Config
import database_api
import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

import src.database.schema  # noqa: F401
from src.database.seed import seed_data

# Ensure the project root is in sys.path for imports
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
  os.environ.setdefault('DATABASE_URL', database_url)

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
      with urlopen(health_url, timeout=2):
        return
    except HTTPError:
      # HTTPError means the server responded with a status (404, 500 etc.)
      # which indicates the backend process is up and listening.
      return
    except URLError:
      time.sleep(0.5)
  raise RuntimeError(f'Backend did not become ready at {health_url} within {timeout_seconds} seconds.')


def _wait_url_ready(url: str, timeout_seconds: int):
  deadline = time.time() + timeout_seconds
  while time.time() < deadline:
    try:
      with urlopen(url, timeout=2):
        return
    except URLError:
      time.sleep(0.5)
  raise RuntimeError(f'Service did not become ready at {url} within {timeout_seconds} seconds.')


@pytest.fixture(scope='session')
def frontend_url() -> str:
  return os.environ.get('E2E_FRONTEND_URL', 'http://localhost:3000/').rstrip('/') + '/'


@pytest.fixture(scope='session')
def backend_url() -> str:
  return _normalize_local_url(os.environ.get('E2E_BACKEND_URL', 'http://127.0.0.1:8080/'))


@pytest.fixture(scope='session')
def backend_server(backend_url: str, database_engine):
  parsed = urlparse(backend_url)
  if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
    pytest.fail(f'Invalid E2E_BACKEND_URL: {backend_url}')
  if parsed.scheme != 'http':
    pytest.fail(f'E2E_BACKEND_URL must be http for local test server startup. Got: {backend_url}')
  if parsed.path not in {'', '/'}:
    pytest.fail(f'E2E_BACKEND_URL must not include a path. Got: {backend_url}')

  project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
  env = os.environ.copy()
  existing_pythonpath = env.get('PYTHONPATH')
  env['PYTHONPATH'] = f'{project_root}{os.pathsep}{existing_pythonpath}' if existing_pythonpath else project_root
  env['LOCAL_PORT'] = str(parsed.port or 8080)
  env.setdefault('IS_DEV', '1')
  env.setdefault('DECODE_JWT_TOKEN', 'dummy')
  # API_PREFIX may be set as a project-level CI/CD variable for production deployments.
  # Unset it for the test server so the PrefixMiddleware is not applied and all
  # routes are reachable at their plain paths (e.g. /user/login, not /api/user/login).
  env.pop('API_PREFIX', None)

  command = [
    sys.executable,
    '-c',
    (
      'import os; from src.__main__ import app; '
      'app.run(host=os.environ.get("E2E_BACKEND_HOST", "127.0.0.1"), '
      'port=int(__import__("os").environ["LOCAL_PORT"]), '
      'debug=False, use_reloader=False)'
    ),
  ]

  process = subprocess.Popen(
    command,
    cwd=project_root,
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
  )

  startup_timeout = int(os.environ.get('E2E_BACKEND_STARTUP_TIMEOUT', '20'))
  try:
    _wait_backend_ready(backend_url, startup_timeout)
  except Exception as exc:
    process.terminate()
    try:
      stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
      process.kill()
      stdout, stderr = process.communicate()
    pytest.fail(f'Failed to start backend at {backend_url}: {exc}\nstdout:\n{stdout}\nstderr:\n{stderr}')

  # Verify the login endpoint actually works before running browser tests.
  # This catches DB connectivity or seed issues early with a clear error message.
  from src.database.seed import _encrypt_seed_password  # noqa: PLC0415

  _login_payload = _json.dumps(
    {
      'email': 'admin',
      'password': _encrypt_seed_password('1234admin'),
    }
  ).encode('utf-8')
  _login_req = urllib.request.Request(
    f'{backend_url}/user/login',
    data=_login_payload,
    headers={'Content-Type': 'application/json'},
    method='POST',
  )
  try:
    try:
      with urlopen(_login_req, timeout=10) as _resp:
        _login_data = _json.loads(_resp.read())
    except HTTPError as _e:
      _raw = _e.read()
      try:
        _login_data = _json.loads(_raw)
      except Exception:
        _login_data = {'status': 'ko', 'raw': _raw.decode('utf-8', errors='replace'), 'http_status': _e.code}
  except URLError as _exc:
    process.terminate()
    try:
      stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
      process.kill()
      stdout, stderr = process.communicate()
    pytest.fail(
      f'Login endpoint not reachable at {backend_url}/user/login: {_exc}\nstdout:\n{stdout}\nstderr:\n{stderr}'
    )
  if _login_data.get('status') != 'ok':
    process.terminate()
    try:
      stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
      process.kill()
      stdout, stderr = process.communicate()
    pytest.fail(
      f'Backend login endpoint not working (expected status=ok): {_login_data}\nstdout:\n{stdout}\nstderr:\n{stderr}'
    )

  yield backend_url

  process.terminate()
  try:
    stdout, stderr = process.communicate(timeout=10)
  except subprocess.TimeoutExpired:
    process.kill()
    stdout, stderr = process.communicate()
  with open('backend_stdout.log', 'w') as _f:
    _f.write(stdout or '')
  with open('backend_stderr.log', 'w') as _f:
    _f.write(stderr or '')


@pytest.fixture(scope='session')
def selenium_remote_url() -> str | None:
  return os.environ.get('SELENIUM_REMOTE_URL')


@pytest.fixture(scope='session')
def driver(selenium_remote_url: str | None):
  options = Options()
  chrome_binary = os.environ.get('CHROME_BIN')
  if chrome_binary:
    options.binary_location = chrome_binary
  options.add_argument('--headless=new')
  options.add_argument('--no-sandbox')
  options.add_argument('--disable-dev-shm-usage')
  options.add_argument('--window-size=1440,1000')
  # Snap-packaged Chromium in this environment fails to create a session
  # unless Chrome exposes a fixed DevTools port.
  options.add_argument(f'--remote-debugging-port={os.environ.get("E2E_CHROME_DEBUG_PORT", "9222")}')

  # Enable browser logging (console / performance) so CI can collect diagnostics
  # Selenium 4 removed `desired_capabilities`; use set_capability on the options object instead.
  options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})

  if selenium_remote_url:
    browser = webdriver.Remote(command_executor=selenium_remote_url, options=options)
  else:
    browser = webdriver.Chrome(options=options)

  yield browser

  # On teardown, dump browser logs to files for artifact collection.
  try:
    try:
      logs = browser.get_log('browser')
    except Exception:
      logs = []
    with open('browser_console.log', 'w') as f:
      for entry in logs:
        # entry keys: level, message, timestamp
        f.write(f'{entry.get("level")} {entry.get("timestamp")} {entry.get("message")}\n')
    try:
      perf = browser.get_log('performance')
      if perf:
        with open('browser_performance.log', 'w') as pf:
          for e in perf:
            pf.write(e.get('message') + '\n')
    except Exception:
      pass
  except Exception:
    pass
  finally:
    browser.quit()


@pytest.fixture
def wait(driver):
  return WebDriverWait(driver, timeout=15)


@pytest.fixture
def frontend_reachable(frontend_url: str):
  try:
    with urlopen(frontend_url, timeout=5):
      return frontend_url
  except URLError as exc:
    pytest.fail(f'Frontend is not reachable at {frontend_url}. Set E2E_FRONTEND_URL correctly. ({exc})')


@pytest.fixture
def e2e_user(request, backend_server: str):
  request.getfixturevalue('database_engine')
  return {'email': 'admin', 'password': '1234admin'}
