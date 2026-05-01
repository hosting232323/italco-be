from datetime import datetime

from ...database.enum import OrderStatus
from ...database.schema import Order, Product
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


def format_data_cloning_order(data: dict):
  new_note = f'Clonato da ordine {data["cloned_order_id"]}'
  data['operator_note'] = f'{new_note}, {data["operator_note"]}' if 'operator_note' in data else new_note
  return data


def format_data_cloning_product(product_data: dict):
  if 'release_place_id' in product_data and product_data['release_place_id']:
    product_data['collection_point_id'] = product_data['release_place_id']
    product_data['release_place_id'] = None
  elif 'on_transport' in product_data and product_data['on_transport']:
    product_data['collection_point_id'] = None
    product_data['on_transport'] = False
  return product_data


def reschedule_check(status: OrderStatus, product: Product, product_data: dict, session):
  if status == OrderStatus.TO_RESCHEDULE:
    if product_data['new_collection_point_id'] == 0:
      update(product, {'on_transport': True}, session=session)
    else:
      update(product, {'release_place_id': product_data['new_collection_point_id']}, session=session)
