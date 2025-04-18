import os

from . import app, IS_DEV
from database_api import set_database


if __name__ == '__main__':
  set_database(
    os.environ['DATABASE_URL'],
    'italco-be' if not IS_DEV else None
  )
  app.run(host='0.0.0.0', port=8080)
