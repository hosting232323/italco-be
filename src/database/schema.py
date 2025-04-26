from sqlalchemy.orm import relationship
from sqlalchemy import Column, Enum, String, Float, Integer, ForeignKey

from api.users.setup import User
from database_api import BaseEntity
from .enum import UserRole, OrderStatus


class ItalcoUser(User):
  __tablename__ = 'italco_user'

  role = Column(Enum(UserRole), nullable=False)
  delivery_group_id = Column(Integer, ForeignKey('delivery_group.id'), nullable=True)

  addressee = relationship('Addressee', back_populates='italco_user')
  service_user = relationship('ServiceUser', back_populates='italco_user')
  delivery_group = relationship('DeliveryGroup', back_populates='italco_user')


class Addressee(BaseEntity):
  __tablename__ = 'addressee'

  name = Column(String, nullable=False)
  address = Column(String, nullable=False)
  city = Column(String, nullable=False)
  cap = Column(String, nullable=False)
  province = Column(String, nullable=False)
  user_id = Column(Integer, ForeignKey('italco_user.id'), nullable=False)

  order = relationship('Order', back_populates='addressee')
  italco_user = relationship('ItalcoUser', back_populates='addressee')


class DeliveryGroup(BaseEntity):
  __tablename__ = 'delivery_group'

  name = Column(String, nullable=False)

  order = relationship('Order', back_populates='delivery_group')
  italco_user = relationship('ItalcoUser', back_populates='delivery_group')


class Order(BaseEntity):
  __tablename__ = 'order'

  status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
  addressee_id = Column(Integer, ForeignKey('addressee.id'), nullable=False)
  service_user_id = Column(Integer, ForeignKey('service_user.id'), nullable=False)
  delivery_group_id = Column(Integer, ForeignKey('delivery_group.id'), nullable=True)
  customer_note = Column(String, nullable=True)
  operator_note = Column(String, nullable=True)
  motivation = Column(String, nullable=True)

  addressee = relationship('Addressee', back_populates='order')
  service_user = relationship('ServiceUser', back_populates='order')
  delivery_group = relationship('DeliveryGroup', back_populates='order')


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
