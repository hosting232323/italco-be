import os
from tqdm import tqdm

from database_api import set_database
from src.database.schema import Order, OrderStatus
from database_api.operations import get_all, update


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])

  orders = get_all(Order)

  for order in tqdm(orders, desc="Aggiornamento delivery_date"):
    if order.status in [OrderStatus.COMPLETED, OrderStatus.CANCELLED]:
      if not getattr(order, "delivery_date", None):
        update(order, {"delivery_date": order.dpc})
