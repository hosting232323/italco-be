from datetime import datetime

from .queries import query_products
from ...database.schema import Order
from ...database.enum import OrderStatus
from ..schedule.queries import get_schedule_by_order
from database_api.operations import update, get_by_id


def update_cloned_order(order: Order, cloned_order_id: int, session):
  cloned_order: Order = get_by_id(Order, cloned_order_id, session=session)
  new_note = f"Rischedulato con l'ordine {order.id}"
  update(
    cloned_order,
    {
      'completion_date': datetime.now(),
      'status': OrderStatus.RESCHEDULED,
      'operator_note': f'{new_note}, {cloned_order.operator_note}' if cloned_order.operator_note else new_note,
    },
    session=session,
  )


def format_data_cloning_order(data: dict, cloned_order_id: int):
  new_note = f'Clonato da ordine {cloned_order_id}'
  data['operator_note'] = f'{new_note}, {data["operator_note"]}' if 'operator_note' in data else new_note
  return data


def format_data_cloning_product(product_data: dict, input_data: dict):
  if 'release_collection_point_id' in input_data and input_data['release_collection_point_id']:
    product_data['collection_point_id'] = input_data['release_collection_point_id']
  elif 'release_transport_id' in input_data and input_data['release_transport_id']:
    product_data['collection_point_id'] = None
    product_data['transport_id'] = input_data['release_transport_id']
  return product_data


def reschedule_products(order: Order, product_data: dict, session):
  order_schedule = get_schedule_by_order(order.id, session=session)
  for product in query_products(order, session=session):
    for product_name in product_data.keys():
      if product.name == product_name:
        if product_data[product_name]['release_collection_point_id'] == 0:
          if order_schedule is None:
            break

          update(product, {'release_transport_id': order_schedule.transport_id}, session=session)
        else:
          update(
            product,
            {'release_collection_point_id': product_data[product_name]['release_collection_point_id']},
            session=session,
          )
        break
