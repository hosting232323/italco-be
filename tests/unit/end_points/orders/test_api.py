from datetime import date, time


import src.end_points.orders.api as orders_api
from src.end_points.orders.api import (
  get_schedule_info_by_order,
  get_transport_by_schedule,
  is_available_order,
  save_order_status_to_euronics,
)

from tests.unit.factories import (
  create_order,
  create_product,
  create_rae_product,
  create_schedule,
  create_transport,
  customer_with_service,
  link_order_to_schedule,
)


def test_save_order_status_skips_without_api_password(db, capsys):
  order = create_order()

  save_order_status_to_euronics(order)  # EURONICS_API_PASSWORD non impostata

  assert 'Euronics Api Key Error' in capsys.readouterr().out


def test_is_available_order_requires_external_id_and_booking_date(db):
  assert is_available_order(create_order()) is False
  assert is_available_order(create_order(external_id='EXT-1')) is False


def test_is_available_order_checks_customer_whitelist(db, monkeypatch):
  customer, _, service_user, _ = customer_with_service()
  order = create_order(external_id='EXT-1', booking_date=date.today())
  create_product(order, service_user)

  assert is_available_order(order) is False

  monkeypatch.setattr(orders_api, 'EURONICS_USER_IDS', [customer.id])
  assert is_available_order(order) is True


def test_get_schedule_info_by_order(db):
  order = create_order()
  schedule = create_schedule()
  item = link_order_to_schedule(order, schedule)

  result = get_schedule_info_by_order(order)

  assert result[0].id == schedule.id
  assert result[1].id == item.id
  assert get_schedule_info_by_order(create_order()) is None


def test_get_transport_by_schedule(db):
  transport = create_transport()
  schedule = create_schedule(transport)

  assert get_transport_by_schedule(schedule).id == transport.id


def test_save_order_status_posts_expected_payload(db, monkeypatch):
  customer, _, service_user, _ = customer_with_service()
  order = create_order(
    external_id='EXT-42', booking_date=date(2026, 7, 20), operator_note='citofono rotto'
  )
  rae_product = create_rae_product(order, customer)
  create_product(order, service_user, rae_product_id=rae_product.id)
  transport = create_transport()
  schedule = create_schedule(transport)
  link_order_to_schedule(
    order, schedule, index=3, start_time_slot=time(8, 0), end_time_slot=time(10, 0)
  )

  captured = {}

  class FakeResponse:
    def raise_for_status(self):
      captured['raised'] = True

  def fake_post(url, json):
    captured['url'] = url
    captured['json'] = json
    return FakeResponse()

  monkeypatch.setattr(orders_api, 'EURONICS_API_PASSWORD', 'secret')
  monkeypatch.setattr(orders_api, 'EURONICS_USER_IDS', [customer.id])
  monkeypatch.setattr(orders_api.requests, 'post', fake_post)

  save_order_status_to_euronics(order)

  booking = captured['json']['ListaBooking'][0]
  assert 'pwd=secret' in captured['url']
  assert booking['id_consegna'] == 'EXT-42'
  assert booking['data_confermata'] == '20/07/2026'
  assert booking['ordinamento'] == '3'
  assert booking['ritiro_rae'] == 1
  assert booking['fascia_oraria'] == '8 - 10'
  assert f'{schedule.id} - {transport.plate}' == booking['rif_vettore']
  assert captured['raised'] is True


def test_save_order_status_without_schedule_uses_defaults(db, monkeypatch):
  customer, _, service_user, _ = customer_with_service()
  order = create_order(external_id='EXT-43', booking_date=date(2026, 7, 21))
  create_product(order, service_user)

  captured = {}

  class FakeResponse:
    def raise_for_status(self):
      pass

  monkeypatch.setattr(orders_api, 'EURONICS_API_PASSWORD', 'secret')
  monkeypatch.setattr(orders_api, 'EURONICS_USER_IDS', [customer.id])
  monkeypatch.setattr(
    orders_api.requests, 'post', lambda url, json: captured.update(json=json) or FakeResponse()
  )

  save_order_status_to_euronics(order)

  booking = captured['json']['ListaBooking'][0]
  assert booking['ordinamento'] == '0'
  assert booking['rif_vettore'] == ''
  assert booking['fascia_oraria'] == ''
  assert booking['ritiro_rae'] == 0
