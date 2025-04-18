from sqlalchemy import Column, Enum

from .enum import UserRole
from api.users.setup import User
from database_api import BaseEntity


class ItalcoUser(User):
  __tablename__ = 'italco_user'

  role = Column(Enum(UserRole), nullable=False)
