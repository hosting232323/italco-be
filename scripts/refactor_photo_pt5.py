from src import DATABASE_URL
from src.database.schema import Photo
from database_api.operations import update
from database_api import set_database, Session


OLD_DOMAIN = "https://ares-logistics.it"
NEW_DOMAIN = "https://test.ares-logistics.it"


def get_all_photos() -> list[Photo]:
  with Session() as session:
    return session.query(Photo).all()


if __name__ == "__main__":
  set_database(DATABASE_URL)

  for photo in get_all_photos():
    if photo.link and photo.link.startswith(OLD_DOMAIN):
      new_link = photo.link.replace(OLD_DOMAIN, NEW_DOMAIN, 1)
      update(photo, {"link": new_link})
