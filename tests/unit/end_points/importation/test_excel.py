import json
from io import BytesIO

import pandas as pd
import pytest

from database_api import Session

from src.database.enum import OrderType, UserRole
from src.database.schema import Order, Product
from src.end_points.importation.excel import build_order, get_collection_point, parse_orders

from tests.unit.factories import (
  auth_header,
  create_collection_point,
  create_service,
  create_service_user,
  create_user,
)


COLUMNS = [
  'Rif. Com',
  'Cod.  Serv',
  'Descr. Serv',
  'LDP',
  'Destinatario',
  'Indirizzo Dest.',
  'Localita',
  'Provincia',
  'CAP',
  'Booking',
  'DRC',
  'Piano',
  'Note MW + Note',
]


def _excel_bytes(rows):
  df = pd.DataFrame(rows, columns=COLUMNS)
  buffer = BytesIO()
  df.to_excel(buffer, index=False)
  buffer.seek(0)
  return buffer


def _base_row(**overrides):
  row = {
    'Rif. Com': 'ORD-1',
    'Cod.  Serv': 'SVC-1',
    'Descr. Serv': 'Lavatrice',
    'LDP': 'Magazzino Bari',
    'Destinatario': 'Mario Rossi',
    'Indirizzo Dest.': 'Via Roma 1',
    'Localita': 'Bari',
    'Provincia': 'BA',
    'CAP': '70121',
    'Booking': '2026-07-20',
    'DRC': '2026-07-18',
    'Piano': '2',
    'Note MW + Note': 'Citofonare',
  }
  row.update(overrides)
  return row


def _customer_with_named_cp(cp_name='Magazzino Bari', service_code='SVC-1'):
  customer = create_user(UserRole.CUSTOMER)
  service = create_service(OrderType.DELIVERY)
  create_service_user(customer, service, code=service_code)
  create_collection_point(customer, name=cp_name)
  return customer


def test_build_order_maps_fields():
  order = build_order(_base_row())

  assert order['type'] == OrderType.DELIVERY
  assert order['addressee'] == 'Mario Rossi'
  assert order['address'] == 'Via Roma 1, Bari, BA'
  assert order['cap'] == '70121'
  assert order['floor'] == 2
  assert order['external_id'] == 'ORD-1'


def test_build_order_handles_empty_floor():
  order = build_order(_base_row(Piano=''))

  assert order['floor'] is None


@pytest.mark.parametrize('piano, atteso', [('2', 2), ('2.0', 2), (' 3 ', 3), ('0', 0)])
def test_build_order_accepts_integer_floors(piano, atteso):
  assert build_order(_base_row(Piano=piano))['floor'] == atteso


@pytest.mark.parametrize('piano', ['1.5', '1,5', 'PT', 'Piano terra', '-1', '2.5.1'])
def test_build_order_discards_non_integer_floors(piano):
  # Scartato, non arrotondato: un piano inventato e' peggio di un piano mancante.
  # Senza questo controllo la cella arriva alla colonna intera e l'INSERT fallisce,
  # interrompendo l'import dopo gli ordini gia' committati.
  assert build_order(_base_row(Piano=piano))['floor'] is None


def test_get_collection_point_trims_names(db):
  customer = create_user(UserRole.CUSTOMER)
  collection_point = create_collection_point(customer, name='Magazzino Bari')

  found = get_collection_point('  Magazzino Bari  ', customer.id)

  assert found.id == collection_point.id
  assert get_collection_point('Inesistente', customer.id) is None


def test_parse_orders_groups_services_and_products(db):
  customer = _customer_with_named_cp()

  orders, error = parse_orders(_excel_bytes([_base_row(), _base_row(**{'Cod.  Serv': 'PRODOTTO'})]), customer.id)

  assert error is None
  assert 'ORD-1' in orders
  assert len(orders['ORD-1']['services']) == 1  # SVC-1 riconosciuto
  assert len(orders['ORD-1']['products']) == 1  # codice non riconosciuto -> prodotto


def test_parse_orders_skips_placeholder_codes(db):
  customer = _customer_with_named_cp()

  orders, error = parse_orders(
    _excel_bytes([_base_row(**{'Cod.  Serv': ''}), _base_row(**{'Cod.  Serv': '404'})]), customer.id
  )

  assert error is None
  assert orders == {}


def test_excel_import_endpoint_creates_orders(client):
  admin = create_user(UserRole.ADMIN)
  customer = _customer_with_named_cp()
  # Un ordine valido richiede esattamente un prodotto (codice sconosciuto) e almeno un servizio (SVC-1)
  rows = [
    _base_row(**{'Cod.  Serv': 'PRODOTTO', 'Descr. Serv': 'Lavatrice'}),
    _base_row(**{'Cod.  Serv': 'SVC-1', 'Descr. Serv': 'Montaggio'}),
  ]

  response = client.post(
    '/import/excel',
    data={
      'customer_id': str(customer.id),
      'file': (_excel_bytes(rows), 'orders.xlsx'),
    },
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['imported_orders_count'] == 1
  with Session() as session:
    order = session.query(Order).filter_by(external_id='ORD-1').one()
    assert session.query(Product).filter_by(order_id=order.id).count() == 1


def test_excel_import_endpoint_reports_conflicts(client):
  admin = create_user(UserRole.ADMIN)
  # Cliente senza punto di ritiro corrispondente -> conflitto
  customer = create_user(UserRole.CUSTOMER)
  create_service_user(customer, create_service(), code='SVC-1')

  response = client.post(
    '/import/excel',
    data={
      'customer_id': str(customer.id),
      'file': (_excel_bytes([_base_row()]), 'orders.xlsx'),
    },
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['imported_orders_count'] == 0
  assert len(body['conflicted_orders']) == 1


def test_excel_import_endpoint_reports_missing_columns(client):
  admin = create_user(UserRole.ADMIN)
  customer = _customer_with_named_cp()
  # File senza le colonne attese (es. formato sbagliato) -> messaggio parlante, niente 500
  buffer = BytesIO()
  pd.DataFrame([{'Colonna A': '1', 'Colonna B': '2'}]).to_excel(buffer, index=False)
  buffer.seek(0)

  response = client.post(
    '/import/excel',
    data={
      'customer_id': str(customer.id),
      'file': (buffer, 'orders.xlsx'),
    },
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'Colonne mancanti' in body['message']
  assert 'Cod.  Serv' in body['message']


def test_excel_import_endpoint_requires_file(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post('/import/excel', data={'customer_id': '1'}, headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Nessun file caricato'


def test_excel_import_endpoint_reads_customer_id_from_data_envelope(client):
  # Il client manda il body in un unico campo 'data' JSON del FormData
  admin = create_user(UserRole.ADMIN)
  customer = _customer_with_named_cp()
  rows = [
    _base_row(**{'Cod.  Serv': 'PRODOTTO', 'Descr. Serv': 'Lavatrice'}),
    _base_row(**{'Cod.  Serv': 'SVC-1', 'Descr. Serv': 'Montaggio'}),
  ]

  response = client.post(
    '/import/excel',
    data={
      'data': json.dumps({'customer_id': customer.id}),
      'file': (_excel_bytes(rows), 'orders.xlsx'),
    },
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['imported_orders_count'] == 1


def test_excel_import_endpoint_reports_missing_customer_id(client):
  # Senza punto vendita deve rispondere ko, non 400: un HTTPException lascerebbe il client in caricamento
  admin = create_user(UserRole.ADMIN)

  response = client.post(
    '/import/excel',
    data={'data': json.dumps({}), 'file': (_excel_bytes([_base_row()]), 'orders.xlsx')},
    headers=auth_header(admin),
  )

  assert response.status_code == 200
  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Punto vendita non specificato'


def test_handle_excel_conflict_endpoint(client):
  admin = create_user(UserRole.ADMIN)
  customer = create_user(UserRole.CUSTOMER)
  service_user = create_service_user(customer, create_service(), code='SVC-1')
  collection_point = create_collection_point(customer)

  # handle_excel_conflict richiama build_order sui dati grezzi, quindi passiamo la riga Excel
  payload_order = {
    **_base_row(),
    'products': {
      'Lavatrice': {
        'services': [service_user.id],
        'collection_point': {'id': collection_point.id},
      }
    },
  }

  response = client.post('/import/excel/conflict', json={'orders': [payload_order]}, headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ok'
  assert body['imported_orders_count'] == 1
  with Session() as session:
    assert session.query(Product).count() == 1
