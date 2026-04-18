"""
E2E test: Pianificazione Automatica respects MAX_PROFESSIONAL_SERVICES=2.

Uses Playwright (sync API) instead of Selenium so it can run independently of
the Selenium infrastructure.  The test opens a real browser, logs in, fills out
the schedule-suggestion form for today's date, submits it, and asserts that
every returned proposal group contains at most 2 distinct professional services.
"""

import datetime
import re

import pytest
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.e2e

MAX_PROFESSIONAL_SERVICES = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prof_service_ids_in_group(schedule_items: list) -> set:
  """Return the set of unique professional service IDs (or names) across all
  Order items in a single proposal group."""
  ids: set = set()
  for item in schedule_items:
    if item.get('operation_type') != 'Order':
      continue
    for product in item.get('products', {}).values():
      for svc in product.get('services', []):
        if isinstance(svc, dict) and svc.get('professional'):
          ids.add(svc.get('id') or svc.get('name'))
  return ids


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_schedule_proposals_professional_services_limit(frontend_reachable):
  """
  Flow:
  1. Login as admin.
  2. Open "Pianificazione Automatica" dialog (SchedulationForm).
  3. Select today's date from the DateField date-picker.
  4. Set "Dimensione minima gruppo" = 1 (so all 20 seed orders are grouped).
  5. Submit the form.
  6. Capture the /schedule/suggestions API response.
  7. Assert every group has ≤ MAX_PROFESSIONAL_SERVICES=2 distinct professional
     service IDs across its orders.
  """
  today = datetime.date.today()

  with sync_playwright() as pw:
    browser = pw.chromium.launch(
      headless=True,
      args=['--no-sandbox', '--disable-dev-shm-usage'],
    )
    context = browser.new_context(viewport={'width': 1440, 'height': 900})
    page = context.new_page()

    # ── 1. Login ──────────────────────────────────────────────────────────
    page.goto(frontend_reachable)
    page.wait_for_load_state('networkidle')

    # The login page renders two inputs: email (type="email") then password.
    page.locator('input[type="email"]').fill('admin')
    page.locator('input[type="password"]').fill('1234admin')
    page.keyboard.press('Enter')

    page.wait_for_url('**/dashboard**', timeout=20_000)
    page.wait_for_load_state('networkidle')

    # ── 2. Open PIANIFICAZIONE AUTOMATICA dialog ──────────────────────────
    page.get_by_text('Pianificazione Automatica', exact=True).click()
    page.wait_for_selector('.v-overlay--active', timeout=10_000)

    # ── 3. Select today in the DateField ──────────────────────────────────
    # The DateField uses a readonly v-text-field as a v-menu activator.
    # The calendar icon (mdi-calendar) is bound to the activator; clicking
    # it opens the v-date-picker.
    page.locator('.mdi-calendar').first.click()
    page.wait_for_selector('.v-date-picker', timeout=8_000)

    # Today's button has aria-label starting with "Today," (Vuetify 3).
    # Example: "Today, Saturday, April 18, 2026"
    page.locator('button[aria-label^="Today,"]').click()

    # The @change event on v-date-picker in Vuetify 3 does not fire on a simple
    # date-cell click, so DateField.closeMenu() is not called automatically.
    # Close the menu by pressing Escape so the rest of the form is accessible.
    page.keyboard.press('Escape')
    page.wait_for_selector('.v-date-picker', state='hidden', timeout=5_000)

    # ── 4. Set minimum group size = 1 ─────────────────────────────────────
    min_input = page.get_by_label('Dimensione minima gruppo')
    min_input.click(click_count=3)
    min_input.fill('1')

    # ── 5. Submit & capture API response ──────────────────────────────────
    with page.expect_response(
      lambda r: 'schedule/suggestions' in r.url and r.request.method == 'GET',
      timeout=30_000,
    ) as resp_info:
      page.get_by_role('button', name=re.compile(r'Invia', re.IGNORECASE)).click()

    response = resp_info.value
    body = response.json()

    context.close()
    browser.close()

  # ── 6–7. Assertions ───────────────────────────────────────────────────────
  assert body.get('status') == 'ok', f'schedule/suggestions returned non-ok status: {body}'

  groups = body['groups']
  assert len(groups) > 0, 'Expected at least one proposal group from the seed data'

  for i, group in enumerate(groups):
    prof_ids = _prof_service_ids_in_group(group['schedule_items'])
    assert len(prof_ids) <= MAX_PROFESSIONAL_SERVICES, (
      f'Group {i} contains {len(prof_ids)} distinct professional services '
      f'(limit is {MAX_PROFESSIONAL_SERVICES}): {prof_ids}'
    )
