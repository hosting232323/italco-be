import os
from tqdm import tqdm

from src.database.enum import UserRole
from database_api.operations import create
from database_api import set_database, Session
from src.database.schema import DeliveryGroup, Schedule, User


def get_wrong_schedules() -> list[Schedule]:
  with Session() as session:
    return session.query(Schedule).outerjoin(
      DeliveryGroup, Schedule.id == DeliveryGroup.schedule_id
    ).filter(
      DeliveryGroup.schedule_id == None
    ).all()


def get_sample_user() -> User:
  with Session() as session:
    return session.query(User).filter(
      User.role == UserRole.DELIVERY,
      User.nickname == 'delivery',
    ).first()


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])
  delivery_user = get_sample_user()
  for schedule in tqdm(get_wrong_schedules()):
    print(schedule)
    create(DeliveryGroup, {
      'user_id': delivery_user.id,
      'schedule_id': schedule.id
    })
