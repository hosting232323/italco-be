from io import BytesIO

import pandas as pd

from src.database.enum import UserRole

from tests.unit.factories import auth_header, create_order, create_product, create_user, customer_with_service


def test_export_orders_excel_builds_spreadsheet(client):
  admin = create_user(UserRole.ADMIN)
  _, service, service_user, _ = customer_with_service()
  order = create_order(addressee='Cliente Excel', anomaly=True)
  create_product(order, service_user, name='Lavastoviglie')

  response = client.post('/export/orders/excel', json={'order_ids': [order.id]}, headers=auth_header(admin))

  assert response.status_code == 200
  assert 'spreadsheetml' in response.headers['Content-Type']

  df = pd.read_excel(BytesIO(response.get_data()))
  assert df.loc[0, 'ID Ordine'] == order.id
  assert df.loc[0, 'Destinatario'] == 'Cliente Excel'
  assert df.loc[0, 'Prodotti'] == 'Lavastoviglie'
  assert df.loc[0, 'Servizi'] == service.name
  assert df.loc[0, 'Anomalia'] == 'Si'
  assert df.loc[0, 'Ritardo'] == 'No'


def test_export_orders_excel_rejects_empty_selection(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post('/export/orders/excel', json={'order_ids': []}, headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Nessun ordine selezionato'


def test_export_orders_excel_rejects_unknown_orders(client):
  admin = create_user(UserRole.ADMIN)

  response = client.post('/export/orders/excel', json={'order_ids': [987654]}, headers=auth_header(admin))

  body = response.get_json()
  assert body['status'] == 'ko'
  assert body['message'] == 'Nessun ordine trovato'
