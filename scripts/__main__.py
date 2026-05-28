import os
from tqdm import tqdm

from src.database.enum import RaeStatus
from database_api.operations import update
from database_api import set_database, Session
from src.database.schema import RaeProduct, Product, Order, ScheduleItemOrder, ScheduleItem, Schedule


def get_service_users() -> list[tuple[RaeProduct, Schedule]]:
  with Session() as session:
    return session.query(
      RaeProduct, Schedule
    ).outerjoin(
      Product, RaeProduct.id == Product.rae_product_id
    ).outerjoin(
      Order, Product.order_id == Order.id
    ).outerjoin(
      ScheduleItemOrder, ScheduleItemOrder.order_id == Order.id
    ).outerjoin(
      ScheduleItem, ScheduleItem.id == ScheduleItemOrder.schedule_item_id
    ).outerjoin(
      Schedule, Schedule.id == ScheduleItem.schedule_id
    ).filter(
      RaeProduct.status != RaeStatus.GENERATED
    ).all()


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])
  for rae_product, schedule in tqdm(get_service_users()):
    if not schedule:
      print(f'RaeProduct {rae_product.id} non ha schedule associato')
      continue

    update(rae_product, {'emission_date': schedule.created_at})
