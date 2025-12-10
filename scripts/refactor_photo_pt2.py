import os
import json
from tqdm import tqdm

from src.database.schema import Photo
from database_api import set_database
from src import STATIC_FOLDER, DATABASE_URL
from database_api.operations import create, get_by_id


def get_old_photos():
  with open('scripts/photos.json', 'r', encoding='utf-8') as file:
    return json.load(file)


if __name__ == '__main__':
  set_database(DATABASE_URL)

  old_photos = get_old_photos()
  for filename in tqdm(os.listdir(STATIC_FOLDER)):
    id, _ = os.path.splitext(filename)
    old_data = next((photo for photo in old_photos if photo['id'] == int(id)), None)
    if not old_data:
      print(f'Filename {filename} non corrispondente con id')
      continue
    if get_by_id(Photo, int(id)):
      print(f'Filename {filename} corrisponde a foto già salvata')
      continue

    create(Photo, {'id': int(id), 'order_id': old_data['order_id'], 'link': f'https://ares-logistics.it/api/{filename}'})
