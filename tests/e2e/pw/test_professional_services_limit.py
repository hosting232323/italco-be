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

# JavaScript che recupera le `suggestions` dal setupState del componente
# SchedulationForm risalendo la catena dei parent Vue a partire dalla prima
# card "Proposta Borderò" nel DOM.
_JS_GET_SUGGESTIONS = """
() => {
  const card = Array.from(document.querySelectorAll('.v-dialog .v-card'))
    .find(c => c.querySelector('.v-card-title')?.textContent.includes('Proposta Borderò'));
  if (!card) return null;
  let comp = card.__vueParentComponent;
  for (let i = 0; comp && i < 20; i++, comp = comp.parent) {
    const state = comp.setupState || comp.data;
    if (state?.suggestions && Array.isArray(state.suggestions))
      return JSON.parse(JSON.stringify(state.suggestions));
  }
  return null;
}
"""


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

  # ── Leggi le proposte dallo stato Vue ─────────────────────────────────────
  suggestions = None
  for _ in range(10):
    suggestions = page.evaluate(_JS_GET_SUGGESTIONS)
    if suggestions:
      break
    page.wait_for_timeout(500)

  assert suggestions, 'Impossibile leggere le proposte dallo stato Vue'
  assert len(suggestions) > 0, 'Nessuna proposta ricevuta dal backend'

  # ── Verifica il limite per ogni proposta ──────────────────────────────────
  for i, suggestion in enumerate(suggestions):
    pro_count = _count_professional_orders(suggestion.get('orders', []))
    assert pro_count <= MAX_PROFESSIONAL_ORDERS, (
      f'Proposta Borderò {i + 1} ha {pro_count} ordini professionali '
      f'(limite: {MAX_PROFESSIONAL_ORDERS})'
    )
