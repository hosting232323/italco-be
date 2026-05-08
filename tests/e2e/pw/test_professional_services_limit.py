"""
E2E test (Playwright): Pianificazione Automatica rispetta MAX_PROFESSIONAL_ORDERS=2.

Flusso completamente browser-based — nessuna chiamata API diretta:
1. Login come admin.
2. Click su "Pianificazione Automatica".
3. Imposta min_size_group = 1.
4. Click "Invia", attesa card "Proposta Borderò N".
5. Legge i dati delle proposte dallo stato Vue tramite evaluate().
6. Assert che ogni proposta abbia ≤ MAX_PROFESSIONAL_ORDERS ordini con
   almeno un servizio professional=True.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

MAX_PROFESSIONAL_ORDERS = 2

def _extract_suggestions(payload):
  """Estrae ricorsivamente i gruppi/proposte dal payload JSON."""
  if isinstance(payload, list):
    # candidato diretto: lista di proposte con chiave orders
    if payload and all(isinstance(item, dict) for item in payload):
      if any('orders' in item for item in payload):
        return payload
    for item in payload:
      found = _extract_suggestions(item)
      if found:
        return found
    return None

  if isinstance(payload, dict):
    groups = payload.get('groups')
    if isinstance(groups, list):
      return groups

    direct = payload.get('suggestions')
    if isinstance(direct, list):
      return direct

    for value in payload.values():
      found = _extract_suggestions(value)
      if found:
        return found

  return None


def _count_professional_orders(orders: list) -> int:
  """Conta gli ordini con almeno un servizio professional=True."""
  count = 0
  for order in orders:
    if order.get('operation_type') != 'Order':
      continue
    for product in (order.get('products') or {}).values():
      if any(s.get('professional') for s in (product.get('services') or [])):
        count += 1
        break
  return count


def test_schedule_proposals_professional_services_limit(pw_page: Page):
  page = pw_page
  captured_suggestions = []

  def _capture_suggestions(response):
    try:
      content_type = response.headers.get('content-type', '').lower()
      if 'application/json' not in content_type:
        return
      payload = response.json()
      suggestions = _extract_suggestions(payload)
      if suggestions:
        captured_suggestions.append(suggestions)
    except Exception:
      # Alcune risposte non sono JSON o non sono pertinenti.
      return

  page.on('response', _capture_suggestions)

  # ── Apri il dialog ────────────────────────────────────────────────────────
  page.get_by_role('button', name='Pianificazione Automatica').click()
  expect(page.locator('.v-dialog')).to_be_visible(timeout=10_000)

  # ── Seleziona la data odierna nel DateField "Data Work" ───────────────────
  # Il DateField è un v-text-field readonly che apre un v-date-picker al click
  date_field = page.locator('.v-dialog .v-text-field').filter(has_text='Data Work')
  date_field.click()
  page.wait_for_selector('.v-date-picker-month', timeout=5_000)
  # Clicca il giorno odierno: ha aria-current="date" sul button
  page.locator('.v-date-picker-month__day-btn[aria-current="date"]').click()
  # Chiudi il picker se rimane aperto
  page.keyboard.press('Escape')

  # ── Imposta min_size_group = 1 ────────────────────────────────────────────
  min_input = page.locator('.v-dialog input[type="number"]').first
  min_input.click()
  min_input.fill('1')

  # ── Invia ─────────────────────────────────────────────────────────────────
  page.locator('.v-dialog').get_by_role('button', name='INVIA').click()

  # ── Attendi le card delle proposte ────────────────────────────────────────
  expect(page.get_by_text('Proposta Borderò 1')).to_be_visible(timeout=30_000)

  # ── Leggi le proposte dalla risposta API (robusto in build production) ───
  for _ in range(20):
    if captured_suggestions:
      break
    page.wait_for_timeout(500)

  page.remove_listener('response', _capture_suggestions)

  suggestions = captured_suggestions[-1] if captured_suggestions else None

  assert suggestions, 'Impossibile leggere le proposte dalla risposta API'
  assert len(suggestions) > 0, 'Nessuna proposta ricevuta dal backend'

  # ── Verifica il limite per ogni proposta ──────────────────────────────────
  for i, suggestion in enumerate(suggestions):
    orders = suggestion.get('orders') or suggestion.get('schedule_items') or []
    pro_count = _count_professional_orders(orders)
    assert pro_count <= MAX_PROFESSIONAL_ORDERS, (
      f'Proposta Borderò {i + 1} ha {pro_count} ordini professionali '
      f'(limite: {MAX_PROFESSIONAL_ORDERS})'
    )
