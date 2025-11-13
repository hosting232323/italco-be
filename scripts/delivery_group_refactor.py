import os
import json
from tqdm import tqdm

from database_api import set_database
from database_api.operations import create
from src.database.schema import DeliveryGroup


DELIVERY_USER_MAP = {
  16: [8, 19],
  3: [17, 19],
  4: [6, 5],
  12: [19, 8],
  6: [7, 27],
  25: [26, 6],
  10: [28, 29],
  18: [28],
  20: [17, 26],
  11: [7, 30],
  17: [5, 19],
  15: [7, 27],
  13: [30, 31],
  21: [], # Squadra consegne aggiuntive??
  5: [6, 8],
  19: [26, 8, 19],
  24: [], # Squadra 1??
  8: [7, 31],
  23: [29, 30],
  1: [], # Squadra Trony Taranto??
  22: [31, 32],
  14: [5, 6],
  9: [5, 19],
  7: [27, 31]
}


def read_schedule_by_file():
  with open('scripts/schedule.json', 'r', encoding='utf-8') as file:
    return json.load(file)


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])
  for schedule in tqdm(read_schedule_by_file(), desc='Aggiornamento delivery group'):
    if schedule['delivery_group_id'] in DELIVERY_USER_MAP:
      if len(DELIVERY_USER_MAP[schedule['delivery_group_id']]):
        for user_id in DELIVERY_USER_MAP[schedule['delivery_group_id']]:
          create(DeliveryGroup, {
            'user_id': user_id,
            'schedule_id': schedule['id']
          })
      else:
        print(f'Schedule {schedule["id"]} problema nessun utente')
    else:
      print(f'Schedule {schedule["id"]} problema non presente delivery_group_id')
