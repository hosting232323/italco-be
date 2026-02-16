import requests
from sqlalchemy import and_

from database_api import Session
from ... import EURONICS_API_PASSWORD
from database_api.operations import get_by_id
from ...database.schema import (
  Order,
  Schedule,
  ScheduleItem,
  ScheduleItemOrder,
  User,
  ServiceUser,
  Product,
  Transport,
  RaeProduct,
)


# Migliorare con thread paralleli
# Usare GDO Euronics
EURONICS_USER_IDS = [42, 43, 44, 45]


def save_order_status_to_euronics(order: Order):
  if not EURONICS_API_PASSWORD:
    print('Api Key Error')
    return

  if not is_available_order(order):
    return

  tupla = get_schedule_info_by_order(order)
  requests.post(
    f'https://delivery.siemdistribuzione.it/Api/DeliveryVettoriAPI/AggiornaBooking/?user=cptrasporti&pwd={EURONICS_API_PASSWORD}',
    json={
      'ListaBooking': [
        {
          'note': order.operator_note,
          'id_consegna': order.external_id,
          'ordinamento': str(tupla[1].index) if tupla else '0',
          'data_confermata': order.booking_date.strftime('%d/%m/%Y'),
          'ritiro_rae': 1 if len(get_rae_products_by_order(order)) > 0 else 0,
          'rif_vettore': f'{tupla[0].id} - {get_transport_by_schedule(tupla[0]).plate}' if tupla else '',
          'fascia_oraria': f'{tupla[1].start_time_slot.split(":")[0]} - {tupla[1].end_time_slot.split(":")[0]}'
          if tupla
          else '',
        }
      ]
    },
  ).raise_for_status()


def get_schedule_info_by_order(order: Order) -> tuple[Schedule, ScheduleItem]:
  with Session() as session:
    return (
      session.query(Schedule, ScheduleItem)
      .join(ScheduleItem, Schedule.id == ScheduleItem.schedule_id)
      .join(
        ScheduleItemOrder,
        and_(ScheduleItemOrder.schedule_item_id == ScheduleItem.id, ScheduleItemOrder.order_id == order.id),
      )
      .first()
    )


def get_transport_by_schedule(schedule: Schedule) -> Transport:
  return get_by_id(Transport, schedule.transport_id)


def get_rae_products_by_order(order: Order) -> list[RaeProduct]:
  with Session() as session:
    return (
      session.query(RaeProduct)
      .join(Product, and_(Product.rae_product_id == RaeProduct.id, Product.order_id == order.id))
      .all()
    )


def is_available_order(order: Order) -> bool:
  if not order.external_id or not order.booking_date:
    return False

  with Session() as session:
    return (
      session.query(User)
      .join(ServiceUser, User.id == ServiceUser.user_id)
      .join(Product, and_(ServiceUser.id == Product.service_user_id, Product.order_id == order.id))
      .first()
      .id
    ) in EURONICS_USER_IDS
