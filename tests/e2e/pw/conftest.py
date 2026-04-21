"""
Fixtures Playwright per i test E2E della sottocartella pw/.

Eredita il setup di database/backend dal conftest padre (tests/e2e/conftest.py)
e aggiunge la fixture `pw_page` — una Page Playwright già loggata come admin —
che i test Playwright usano al posto del driver Selenium.
"""

import pytest
from playwright.sync_api import Page

# ── re-use backend/db fixtures from the parent conftest ──────────────────────
# Le fixture `backend_server`, `database_engine`, `frontend_url` e `e2e_user`
# sono definite in tests/e2e/conftest.py e vengono rilevate automaticamente
# da pytest grazie alla gerarchia delle directory.


@pytest.fixture(scope='session')
def pw_base_url(frontend_url: str) -> str:
  return frontend_url.rstrip('/')


@pytest.fixture
def pw_page(page: Page, pw_base_url: str, e2e_user: dict, backend_server: str) -> Page:
  """Page Playwright già autenticata come admin sulla dashboard."""
  page.goto(f'{pw_base_url}/')

  page.locator("input[type='email'], input[name='email']").fill(e2e_user['email'])
  pwd = page.locator("input[type='password'], input[name='password']")
  pwd.fill(e2e_user['password'])
  pwd.press('Enter')

  page.wait_for_url('**/dashboard', timeout=15_000)
  return page
