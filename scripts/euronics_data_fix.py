import os
from tqdm import tqdm

from database_api import set_database
from database_api.operations import update

from src.end_points.importation.api import call_list_euronics_api
from src.end_points.users.queries import get_user_and_collection_point_by_code
from src.end_points.orders.queries import get_order_by_external_id_and_customer


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])

  for imported_order in tqdm(call_list_euronics_api()):
    result = get_user_and_collection_point_by_code(imported_order['cod_pv'])
    if not result or not result[0]:
      print(f'Non trovato punto vendita {imported_order["cod_pv"]}')
      continue

    order = get_order_by_external_id_and_customer(imported_order['id_consegna'], result[0].id)
    if not order:
      print(f'Ordine {imported_order['id_consegna']} non trovato')

    update(order, {'external_link': imported_order['url']})
