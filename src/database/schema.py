from sqlalchemy.orm import relationship
from sqlalchemy import Column, Enum, String, Float, Integer, ForeignKey

from api.users.setup import User
from database_api import BaseEntity
from .enum import UserRole, OrderStatus


class ItalcoUser(User):
  __tablename__ = 'italco_user'

  role = Column(Enum(UserRole), nullable=False)

  service_user = relationship('ServiceUser', back_populates='italco_user')


class Order(BaseEntity):
  __tablename__ = 'order'

  service_user_id = Column(Integer, ForeignKey('service_user.id'), nullable=False)
  point_of_sale = Column(String, nullable=False)
  status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
  note = Column(String, nullable=True)
  group = Column(String, nullable=True)
  motivation = Column(String, nullable=True)

  service_user = relationship('ServiceUser', back_populates='order')


class Service(BaseEntity):
  __tablename__ = 'service'

  name = Column(String, nullable=False)
  description = Column(String, nullable=True)

  service_user = relationship('ServiceUser', back_populates='service')


class ServiceUser(BaseEntity):
  __tablename__ = 'service_user'

  user_id = Column(Integer, ForeignKey('italco_user.id'), nullable=False)
  service_id = Column(Integer, ForeignKey('service.id'), nullable=False)
  price = Column(Float(), nullable=False)

  order = relationship('Order', back_populates='service_user')
  service = relationship('Service', back_populates='service_user')
  italco_user = relationship('ItalcoUser', back_populates='service_user')
