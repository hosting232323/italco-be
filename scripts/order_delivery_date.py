import os
from tqdm import tqdm

from database_api import set_database
from src.database.schema import Order, OrderStatus
from database_api.operations import get_all, update


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])

  orders: list[Order] = get_all(Order)

  for order in tqdm(orders, desc='Aggiornamento delivery_date'):
    if order.status in [OrderStatus.DELIVERED, OrderStatus.NOT_DELIVERED]:
      if not order.booking_date:
        update(order, {'booking_date': order.dpc})
