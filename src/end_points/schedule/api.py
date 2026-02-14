import requests
from sqlalchemy import and_

from database_api import Session
from ... import EURONICS_API_PASSWORD
from database_api.operations import get_by_id
from ...database.schema import Schedule, Transport, Order, Product, RaeProduct, User, ServiceUser


# Migliorare con thread paralleli
# Usare GDO Euronics
EURONICS_USER_IDS = [42, 43, 44, 45]


def save_info_to_euronics(schedule: Schedule, schedule_items: list[dict]):
  if not EURONICS_API_PASSWORD:
    print('Api Key Error')
    return

  transport: Transport = get_by_id(Transport, schedule.transport_id)
  booking_list = [
    {
      'ordinamento': str(index),
      'note': item['order'].operator_note,
      'id_consegna': item['order'].external_id,
      'rif_vettore': f'{schedule.id} - {transport.plate}',
      'data_confermata': schedule.date.strftime('%d/%m/%Y'),
      'ritiro_rae': 1 if len(get_rae_products_by_order(item['order'])) > 0 else 0,
      'fascia_oraria': f'{item["start_time_slot"].split(":")[0]} - {item["end_time_slot"].split(":")[0]}',
    }
    for index, item in enumerate(schedule_items)
    if item['operation_type'] == 'Order' and is_available_order(item['order'])
  ]

  if len(booking_list) > 0:
    requests.post(
      f'https://delivery.siemdistribuzione.it/Api/DeliveryVettoriAPI/AggiornaBooking/?user=cptrasporti&pwd={EURONICS_API_PASSWORD}',
      json={'ListaBooking': booking_list},
    ).raise_for_status()


def get_rae_products_by_order(order: Order) -> list[RaeProduct]:
  with Session() as session:
    return (
      session.query(RaeProduct)
      .join(Product, and_(Product.rae_product_id == RaeProduct.id, Product.order_id == order.id))
      .all()
    )


def is_available_order(order: Order) -> bool:
  if not order.external_id:
    return False

  with Session() as session:
    return (
      session.query(User)
      .join(ServiceUser, User.id == ServiceUser.user_id)
      .join(Product, and_(ServiceUser.id == Product.service_user_id, Product.order_id == order.id))
      .first()
      .id
    ) in EURONICS_USER_IDS
