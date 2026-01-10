from src import DATABASE_URL
from src.database.schema import Photo
from database_api.operations import update
from database_api import set_database, Session


def get_all_photos() -> list[Photo]:
  with Session() as session:
    return session.query(Photo).all()


if __name__ == '__main__':
  set_database(DATABASE_URL)
  for photo in get_all_photos():
    update(photo, {'link': photo.link.replace('/photos/', '/photos/prod/')})
