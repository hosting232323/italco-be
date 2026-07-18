from datetime import date

import pytest
from database_api import Session
from database_api.operations import create as database_create

from src.database.schema import CollectionPoint, Order, Product, ServiceUser
from src.end_points.importation import excel as excel_module


def _order_data(service_user_id, collection_point_id, rif):
  return {
    'Rif. Com': rif,
    'Destinatario': 'Mario Rossi',
    'Indirizzo Dest.': 'Via Roma 1',
    'Localita': 'Bari',
    'Provincia': 'BA',
    'CAP': '70121',
    'Booking': date.today().isoformat(),
    'DRC': date.today().isoformat(),
    'Piano': '',
    'Note MW + Note': '',
    'products': {
      'first': {'services': [service_user_id], 'collection_point': {'id': collection_point_id}},
      'second': {'services': [service_user_id], 'collection_point': {'id': collection_point_id}},
    },
  }


def _seed_refs():
  with Session() as session:
    service_user_id = session.query(ServiceUser.id).first()[0]
    collection_point_id = session.query(CollectionPoint.id).first()[0]
  return service_user_id, collection_point_id


def _order_count(external_id):
  with Session() as session:
    return session.query(Order).filter(Order.external_id == external_id).count()


def test_conflict_import_unexpected_error_propagates_and_rolls_back(seeded_db, monkeypatch):
  service_user_id, collection_point_id = _seed_refs()
  product_calls = 0

  def create_then_fail(model, data, session=None):
    nonlocal product_calls
    if model is Product:
      product_calls += 1
      if product_calls == 2:
        raise RuntimeError('second product failed')
    return database_create(model, data, session=session)

  monkeypatch.setattr(excel_module, 'create', create_then_fail)

  with pytest.raises(RuntimeError, match='second product failed'):
    excel_module.handle_excel_conflict([_order_data(service_user_id, collection_point_id, 'rif-bug')])

  assert _order_count('rif-bug') == 0


def test_conflict_import_reports_missing_collection_point_and_continues(seeded_db):
  service_user_id, collection_point_id = _seed_refs()

  response = excel_module.handle_excel_conflict(
    [
      _order_data(service_user_id, 999999, 'rif-ko'),
      _order_data(service_user_id, collection_point_id, 'rif-ok'),
    ]
  )

  assert response['status'] == 'ok'
  assert response['imported_orders_count'] == 1
  assert response['failed_orders'] == [
    {'external_id': 'rif-ko', 'error': 'Punto di ritiro inesistente per il prodotto "first"'}
  ]
  assert _order_count('rif-ko') == 0
  assert _order_count('rif-ok') == 1


def test_conflict_import_reports_nonexistent_service(seeded_db):
  _, collection_point_id = _seed_refs()

  order_data = _order_data(999999, collection_point_id, 'rif-no-service')
  response = excel_module.handle_excel_conflict([order_data])

  assert response['imported_orders_count'] == 0
  assert response['failed_orders'] == [
    {'external_id': 'rif-no-service', 'error': 'Servizi inesistenti per il prodotto "first"'}
  ]
  assert _order_count('rif-no-service') == 0


def test_conflict_import_reports_missing_fields(seeded_db):
  response = excel_module.handle_excel_conflict([{'Rif. Com': 'rif-malformato'}])

  assert response['imported_orders_count'] == 0
  assert len(response['failed_orders']) == 1
  assert response['failed_orders'][0]['external_id'] == 'rif-malformato'
  assert response['failed_orders'][0]['error'].startswith('Campi ordine mancanti')


def test_conflict_import_reports_invalid_date(seeded_db):
  service_user_id, collection_point_id = _seed_refs()

  order_data = _order_data(service_user_id, collection_point_id, 'rif-bad-date')
  order_data['Booking'] = 'non-una-data'
  response = excel_module.handle_excel_conflict([order_data])

  assert response['imported_orders_count'] == 0
  assert response['failed_orders'] == [{'external_id': 'rif-bad-date', 'error': 'Data "Booking" non valida'}]
  assert _order_count('rif-bad-date') == 0


def test_conflict_import_reports_null_collection_point(seeded_db):
  service_user_id, collection_point_id = _seed_refs()

  order_data = _order_data(service_user_id, collection_point_id, 'rif-null-cp')
  order_data['products'] = {'first': {'services': [service_user_id], 'collection_point': None}}
  response = excel_module.handle_excel_conflict([order_data])

  assert response['imported_orders_count'] == 0
  assert response['failed_orders'] == [
    {'external_id': 'rif-null-cp', 'error': 'Punto di ritiro mancante per il prodotto "first"'}
  ]
  assert _order_count('rif-null-cp') == 0


def test_conflict_import_rejects_empty_services_without_creating_orphan_order(seeded_db):
  service_user_id, collection_point_id = _seed_refs()

  order_data = _order_data(service_user_id, collection_point_id, 'rif-empty-services')
  order_data['products'] = {'first': {'services': [], 'collection_point': {'id': collection_point_id}}}
  response = excel_module.handle_excel_conflict([order_data])

  assert response['imported_orders_count'] == 0
  assert response['failed_orders'] == [
    {'external_id': 'rif-empty-services', 'error': 'Servizi mancanti o non validi per il prodotto "first"'}
  ]
  assert _order_count('rif-empty-services') == 0


def test_conflict_import_rejects_non_dict_order_without_500(seeded_db):
  response = excel_module.handle_excel_conflict(['non sono un ordine'])

  assert response['imported_orders_count'] == 0
  assert response['failed_orders'] == [{'external_id': None, 'error': 'Ordine in formato non valido'}]
