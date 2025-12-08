import os
import json
from tqdm import tqdm

from src.database.schema import Photo
from database_api import set_database
from database_api.operations import create
from src import STATIC_FOLDER, DATABASE_URL


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
      raise Exception(f'Filename {filename} non corrispondente con id')

    create(Photo, {'id': int(id), 'order_id': old_data['order_id'], 'link': f'https://ares-logistics.it/api/{filename}'})
