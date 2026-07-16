from datetime import date, datetime


import src.end_points.importation.api as import_api
from src.database.enum import EuronicsStatus, UserRole
from src.database.schema import Order, Product
from src.end_points.importation.api import (
  ORDER_STATUS_MAP,
  format_date,
  product_service_user_handler,
  save_orders_by_euronics,
  update_order_status_by_euronics,
)

from database_api import Session

from tests.unit.factories import (
  create_collection_point,
  create_customer_info,
  create_order,
  create_service,
  create_service_user,
  create_user,
)


def _euronics_order(**overrides):
  base = {
    'cod_pv': 'PV-1',
    'stato': 0,
    'id_consegna': 'EXT-1',
    'dataconferma': '',
    'CAP': '70121',
    'cliente': 'Mario Rossi',
    'url': 'http://euronics/1',
    'data_vendita': '01/07/2026 10:00:00',
    'data_consegna': '05/07/2026 10:00:00',
    'telefono': '080',
    'telefono1': '333',
    'note_conferma': '',
    'indirizzo': 'Via Roma 1',
    'localita': 'Bari',
    'provincia': 'BA',
    'dettaglio': [{'cod_articolo': 'ART-1', 'descrizione': 'Lavatrice'}],
  }
  base.update(overrides)
  return base


def _customer_with_pv():
  customer = create_user(UserRole.CUSTOMER)
  create_customer_info(customer, import_code='PV-1')
  collection_point = create_collection_point(customer)
  return customer, collection_point


def test_format_date_parses_and_handles_empty():
  assert format_date('05/07/2026 10:30:00') == datetime(2026, 7, 5, 10, 30, 0)
  assert format_date('') is None
  assert format_date(None) is None


def test_order_status_map_covers_known_codes():
  assert ORDER_STATUS_MAP[0] is EuronicsStatus.NEW
  assert ORDER_STATUS_MAP[100] is EuronicsStatus.DELETED


def test_save_orders_requires_api_password(db, monkeypatch):
  monkeypatch.setattr(import_api, 'EURONICS_API_PASSWORD', None)

  assert save_orders_by_euronics()['status'] == 'ko'


def test_save_orders_creates_new_orders(db, monkeypatch):
  customer, _ = _customer_with_pv()
  # Il codice '777' è il service_user di fallback usato per i prodotti senza servizio
  create_service_user(customer, create_service(), code='777')
  monkeypatch.setattr(import_api, 'EURONICS_API_PASSWORD', 'secret')
  # cod_articolo sconosciuto -> viene trattato come prodotto (non come servizio)
  monkeypatch.setattr(
    import_api,
    'call_list_euronics_api',
    lambda: [_euronics_order(dettaglio=[{'cod_articolo': 'PROD-1', 'descrizione': 'Lavatrice'}])],
  )

  result = save_orders_by_euronics()

  assert result['status'] == 'ok'
  with Session() as session:
    order = session.query(Order).filter_by(external_id='EXT-1').one()
    assert order.addressee == 'Mario Rossi'
    assert order.external_status is EuronicsStatus.NEW
    assert session.query(Product).filter_by(order_id=order.id).count() == 1


def test_save_orders_skips_unknown_collection_point(db, monkeypatch):
  monkeypatch.setattr(import_api, 'EURONICS_API_PASSWORD', 'secret')
  monkeypatch.setattr(import_api, 'call_list_euronics_api', lambda: [_euronics_order(cod_pv='PV-SCONOSCIUTO')])

  result = save_orders_by_euronics()

  assert result['status'] == 'ok'
  with Session() as session:
    assert session.query(Order).count() == 0


def test_save_orders_updates_existing_order(db, monkeypatch):
  customer, _ = _customer_with_pv()
  create_service_user(customer, create_service(), code='ART-1')
  existing = create_order(external_id='EXT-1', external_status=EuronicsStatus.NEW)
  from tests.unit.factories import create_product

  create_product(existing, create_service_user(customer, create_service(), code='ART-9'))
  monkeypatch.setattr(import_api, 'EURONICS_API_PASSWORD', 'secret')
  monkeypatch.setattr(
    import_api,
    'call_list_euronics_api',
    lambda: [_euronics_order(stato=1, dataconferma='02/07/2026 09:00:00')],
  )

  save_orders_by_euronics()

  with Session() as session:
    refreshed = session.query(Order).filter_by(external_id='EXT-1').one()
    assert refreshed.external_status is EuronicsStatus.DELIVERED
    assert refreshed.confirmed is True
    # La colonna confirmation_date è di tipo Date: il datetime viene troncato al giorno
    assert refreshed.confirmation_date == date(2026, 7, 2)


def test_update_order_status_by_euronics(db, monkeypatch):
  create_order(external_id='EXT-7', external_status=EuronicsStatus.NEW)
  monkeypatch.setattr(import_api, 'EURONICS_API_PASSWORD', 'secret')
  monkeypatch.setattr(
    import_api,
    'call_status_euronics_api',
    lambda status: [{'id_consegna': 'EXT-7', 'stato_consegnato': 1}],
  )

  result = update_order_status_by_euronics(1)

  assert result['status'] == 'ok'
  with Session() as session:
    assert session.query(Order).filter_by(external_id='EXT-7').one().external_status is EuronicsStatus.DELIVERED


def test_update_order_status_requires_api_password(db, monkeypatch):
  monkeypatch.setattr(import_api, 'EURONICS_API_PASSWORD', None)

  assert update_order_status_by_euronics(1)['status'] == 'ko'


def test_product_service_user_handler_without_products_returns_false(db):
  customer, collection_point = _customer_with_pv()
  create_service_user(customer, create_service(), code='ART-1')
  order = create_order()
  imported = _euronics_order(dettaglio=[{'cod_articolo': 'ART-1', 'descrizione': 'Servizio'}])

  with Session() as session:
    order_in_session = session.get(Order, order.id)
    result = product_service_user_handler(imported, customer, collection_point, order_in_session, session)

  assert result is False
