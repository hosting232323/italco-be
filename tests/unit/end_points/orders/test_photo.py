from io import BytesIO

from database_api import Session

from src.database.schema import Photo

from tests.unit.factories import auth_header, create_order, create_product, create_user, customer_with_service
from src.database.enum import UserRole


PNG_BYTES = (
  b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
  b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0'
  b'\x00\x00\x00\x03\x00\x01_\xf5\xd7\xc7\x00\x00\x00\x00IEND\xaeB`\x82'
)


def test_update_order_with_photo_creates_photo_row(client, monkeypatch):
  import src.utils.storage as storage_module

  monkeypatch.setattr(storage_module, 'upload_file', lambda content, filename, folder, **kwargs: f'/fake/{filename}')
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  response = client.put(
    f'/order/{order.id}',
    data={
      'data': '{"id": %d}' % order.id,
      'photo_1': (BytesIO(PNG_BYTES), 'foto.png', 'image/png'),
    },
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  with Session() as session:
    photo = session.query(Photo).filter_by(order_id=order.id).one()
    assert photo.link.endswith(f'{photo.id}.png')
    assert '/order/photos/' in photo.link


def test_update_order_with_signature_saves_binary(client, monkeypatch):
  import src.utils.storage as storage_module

  monkeypatch.setattr(storage_module, 'upload_file', lambda content, filename, folder, **kwargs: f'/fake/{filename}')
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  response = client.put(
    f'/order/{order.id}',
    data={
      'data': '{"id": %d}' % order.id,
      'signature': (BytesIO(PNG_BYTES), 'firma.png', 'image/png'),
    },
    headers=auth_header(admin),
  )

  assert response.get_json()['status'] == 'ok'
  from database_api.operations import get_by_id
  from src.database.schema import Order

  assert get_by_id(Order, order.id).signature == PNG_BYTES


def test_update_order_rejects_non_image_uploads(client):
  admin = create_user(UserRole.ADMIN)
  _, _, service_user, _ = customer_with_service()
  order = create_order()
  create_product(order, service_user)

  response = client.put(
    f'/order/{order.id}',
    data={
      'data': '{"id": %d}' % order.id,
      'malicious': (BytesIO(b'#!/bin/sh'), 'script.sh', 'application/octet-stream'),
    },
    headers=auth_header(admin),
  )

  body = response.get_json()
  assert body['status'] == 'ko'
  assert 'Estensione non supportata' in body['message']
  with Session() as session:
    assert session.query(Photo).filter_by(order_id=order.id).count() == 0
