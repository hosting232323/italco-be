from src import DATABASE_URL
from database_api import set_database


if __name__ == '__main__':
  set_database(DATABASE_URL)
