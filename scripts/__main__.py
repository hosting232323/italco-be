import os
import json
from tqdm import tqdm

from database_api import set_database
from database_api.operations import create
from src.database.schema import Service, ServiceUser


def read_file(file_path):
  with open(file_path, 'r', encoding='utf-8') as file:
    return json.load(file)


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])
  for service in tqdm(read_file('scripts/service.json')):
    create(Service, service)
  for service_user in tqdm(read_file('scripts/service_user.json')):
    create(ServiceUser, service_user)
