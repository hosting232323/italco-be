import os
from tqdm import tqdm

from database_api.operations import update
from src.database.schema import ServiceUser
from database_api import set_database, Session


def get_service_users():
  with Session() as session:
    return session.query(ServiceUser).filter(ServiceUser.code.is_not(None)).all()


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])
  for service_user in tqdm(get_service_users()):
    update(service_user, {'code': service_user.code.strip()})
