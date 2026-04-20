from datetime import date
from sqlalchemy import and_
from sqlalchemy.orm import aliased

from database_api import Session
from .queries import extract_schedule_item
from database_api.operations import get_by_id, update
from ...database.enum import ScheduleType, OrderStatus
from ...database.schema import (
  Schedule,
  User,
  Order,
  DeliveryGroup,
  ScheduleItem,
  ScheduleItemCollectionPoint,
  ScheduleItemReleasePlace,
  ScheduleItemOrder,
  CollectionPoint,
  Product,
  Service,
  ServiceUser,
)


def get_items_for_delivery(delivery_user: User):
  schedule_items = []
  for tupla in query_schedules(delivery_user):
    schedule_items = format_query_result(tupla, schedule_items)
  if len(schedule_items) < 1:
    return {'status': 'ko', 'message': 'Numero di schedule item trovati non valido'}

  return {'status': 'ok', 'schedule_items': schedule_items}


def update_schedule_item(delivery_user: User, schedule_item_id: int, completed: bool):
  schedule_item: ScheduleItem = get_by_id(ScheduleItem, schedule_item_id)
  update(schedule_item, {'completed': completed})

  items_response = get_items_for_delivery(delivery_user)
  if items_response['status'] == 'ko':
    return items_response

  schedule_items = items_response['schedule_items']
  for item in schedule_items:
    if item['operation_type'] == 'CollectionPoint':
      continue

    required_cp_ids = [product['collection_point']['id'] for product in item['products'].values()]
    if all(
      collection_point['completed']
      for collection_point in [
        item
        for item in schedule_items
        if item['operation_type'] == 'CollectionPoint' and item['collection_point']['id'] in required_cp_ids
      ]
    ):
      order: Order = get_by_id(Order, item['order_id'])
      update(order, {'status': OrderStatus.BOOKING})

  return {'status': 'ok', 'message': 'Operazione completata'}


def query_schedules(
  delivery_user: User,
) -> list[tuple[ScheduleItem, CollectionPoint, CollectionPoint, Order, Product, CollectionPoint, Service]]:
  with Session() as session:
    collection_point = aliased(CollectionPoint)
    release_place = aliased(CollectionPoint)
    product_collection_point = aliased(CollectionPoint)
    return (
      session.query(ScheduleItem, collection_point, release_place, Order, Product, product_collection_point, Service)
      .join(Schedule, and_(ScheduleItem.schedule_id == Schedule.id, Schedule.date == date.today()))
      .join(DeliveryGroup, and_(DeliveryGroup.schedule_id == Schedule.id, DeliveryGroup.user_id == delivery_user.id))
      .outerjoin(
        ScheduleItemCollectionPoint,
        and_(
          ScheduleItem.operation_type == ScheduleType.COLLECTION_POINT,
          ScheduleItemCollectionPoint.schedule_item_id == ScheduleItem.id,
        ),
      )
      .outerjoin(collection_point, collection_point.id == ScheduleItemCollectionPoint.collection_point_id)
      .outerjoin(
        ScheduleItemReleasePlace,
        and_(
          ScheduleItem.operation_type == ScheduleType.RELEASE_PLACE,
          ScheduleItemReleasePlace.schedule_item_id == ScheduleItem.id,
        ),
      )
      .outerjoin(release_place, release_place.id == ScheduleItemReleasePlace.collection_point_id)
      .outerjoin(
        ScheduleItemOrder,
        and_(ScheduleItem.operation_type == ScheduleType.ORDER, ScheduleItemOrder.schedule_item_id == ScheduleItem.id),
      )
      .outerjoin(Order, ScheduleItemOrder.order_id == Order.id)
      .outerjoin(Product, Order.id == Product.order_id)
      .outerjoin(product_collection_point, product_collection_point.id == Product.collection_point_id)
      .outerjoin(ServiceUser, Product.service_user_id == ServiceUser.id)
      .outerjoin(Service, ServiceUser.service_id == Service.id)
      .order_by(ScheduleItem.index)
      .all()
    )


def format_query_result(
  tupla: tuple[ScheduleItem, CollectionPoint, CollectionPoint, Order, Product, CollectionPoint, Service], list: list[dict]
) -> list[dict]:
  if tupla[0].operation_type == ScheduleType.COLLECTION_POINT and tupla[1]:
    schedule_item = tupla[1].to_dict()
    schedule_item['collection_point'] = tupla[1].id
  elif tupla[0].operation_type == ScheduleType.RELEASE_PLACE and tupla[2]:
    schedule_item = tupla[2].to_dict()
    schedule_item['collection_point'] = tupla[2].id
  elif tupla[0].operation_type == ScheduleType.ORDER and tupla[3]:
    for element in list:
      if element['id'] == tupla[0].id:
        if tupla[4].name not in element['products']:
          element['products'][tupla[4].name] = extract_product(tupla[5], tupla[6])
          return list
        elif tupla[6].name not in element['products'][tupla[4].name]['services']:
          element['products'][tupla[4].name]['services'].append(tupla[6].name)
          return list

    schedule_item = tupla[3].to_dict()
    schedule_item['order_id'] = tupla[3].id
    schedule_item['products'] = {tupla[4].name: extract_product(tupla[5], tupla[6])}
  else:
    return list

  list.append(extract_schedule_item(schedule_item, tupla[0]))
  return list


def extract_product(collection_point: CollectionPoint, service: Service) -> dict:
  return {
    'services': [service.name],
    'collection_point': {
      'id': collection_point.id,
      'name': collection_point.name
    }
  }
