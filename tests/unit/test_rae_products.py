from datetime import datetime, timezone

from database_api import Session
from database_api.operations import create

from src.database.enum import RaeStatus
from src.database.schema import DtrDocument, Order, RaeProduct, RaeProductGroup, User
from src.end_points.rae.product import get_rae_products


def test_get_rae_products_joins_and_formats_latest_dtr_document(seeded_db):
  with Session() as session:
    user = session.query(User).first()
    order = session.query(Order).first()
    group = create(
      RaeProductGroup,
      {'name': 'Test RAE', 'cer_code': 123456, 'group_code': 'R1'},
      session=session,
    )
    product = create(
      RaeProduct,
      {
        'user_id': user.id,
        'order_id': order.id,
        'rae_product_group_id': group.id,
        'status': RaeStatus.GENERATED,
      },
      session=session,
    )
    session.add_all(
      [
        DtrDocument(
          link='old-dtr.pdf',
          rae_product_id=product.id,
          created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        ),
        DtrDocument(
          link='latest-dtr.pdf',
          rae_product_id=product.id,
          created_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        ),
      ]
    )
    session.commit()
    product_id = product.id
    response = get_rae_products(user, [])
  products = {item['id']: item for item in response['rae_products']}

  assert response['status'] == 'ok'
  assert products[product_id]['link'] == 'latest-dtr.pdf'
