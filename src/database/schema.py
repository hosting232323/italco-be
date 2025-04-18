from sqlalchemy import Column, Enum, String

from api.users.setup import User
from database_api import BaseEntity
from .enum import UserRole, OrderStatus


class ItalcoUser(User):
  __tablename__ = 'italco_user'

  role = Column(Enum(UserRole), nullable=False)


class Order(BaseEntity):
  __tablename__ = 'order'

  service = Column(String(), nullable=False)
  point_of_sale = Column(String(), nullable=False)
  status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
  note = Column(String(), nullable=True)
  group = Column(String(), nullable=True)
  motivation = Column(String(), nullable=True)
