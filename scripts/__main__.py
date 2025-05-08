import os
import json
from tqdm import tqdm

from database_api import set_database
from src.database.schema import Order
from database_api.operations import update, get_by_id


def read_file(file_path):
  with open(file_path, 'r', encoding='utf-8') as file:
    return json.load(file)


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])
  products = read_file('scripts/product.json')
  for order_product in tqdm(read_file('scripts/order_product.json')):
    order: Order = get_by_id(Order, order_product['order_id'])
    if not order.products:
      order.products = []
    update(order, {
      'products': order.products + [next((
        product['name'] for product in products if product['id'] == order_product['product_id']
      ), 0)]
    })
