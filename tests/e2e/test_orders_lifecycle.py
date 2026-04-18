import pytest
from selenium.webdriver.common.by import By

from tests.e2e.order_lifecycle_flow import (
  OrderLifecycleData,
  add_product_row,
  click_submit,
  fill_operator_form,
  login_and_open_create_dialog,
  open_order_operator_form,
  run_order_lifecycle,
)

pytestmark = pytest.mark.e2e


def _visible_text(driver):
  return driver.find_element(By.TAG_NAME, 'body').text


def test_order_lifecycle_admin_creates_order(driver, wait, frontend_reachable, e2e_user, backend_server):
  run_order_lifecycle(driver, wait, frontend_reachable, e2e_user)


def test_customer_step_requires_punto_vendita_selection(driver, wait, frontend_reachable, e2e_user, backend_server):
  login_and_open_create_dialog(driver, wait, frontend_reachable, e2e_user)
  click_submit(driver, wait)

  user_id = driver.execute_script("""
    const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
    const orderStore = pinia?._s?.get('order');
    return orderStore?.element?.user_id ?? null;
  """)

  page = _visible_text(driver)
  assert 'Punto Vendita' in page
  assert user_id is None


def test_order_form_blocks_invalid_address_without_google_selection(
  driver, wait, frontend_reachable, e2e_user, backend_server
):
  open_order_operator_form(driver, wait, frontend_reachable, e2e_user)
  add_product_row(driver, wait)
  fill_operator_form(driver, wait, OrderLifecycleData(), bypass_google_places=False)
  click_submit(driver, wait)

  page = _visible_text(driver)
  assert 'Seleziona un indirizzo valido da Google Places' in page


def test_order_dialog_can_be_opened_and_closed(driver, wait, frontend_reachable, e2e_user, backend_server):
  login_and_open_create_dialog(driver, wait, frontend_reachable, e2e_user)
  close_btn = wait.until(
    lambda d: next(
      (el for el in d.find_elements(By.CSS_SELECTOR, 'button i.mdi-close, button .mdi-close') if el.is_displayed()),
      False,
    )
  )
  close_btn.click()
  assert 'Crea Ordine' not in _visible_text(driver)
