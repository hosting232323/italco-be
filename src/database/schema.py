from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy import Column, Enum, Date, String, Float, Integer, LargeBinary, ForeignKey

from api.users.setup import User
from database_api import BaseEntity
from .enum import UserRole, OrderStatus, OrderType


class ItalcoUser(User):
  __tablename__ = 'italco_user'

  role = Column(Enum(UserRole), nullable=False)
  delivery_group_id = Column(Integer, ForeignKey('delivery_group.id'), nullable=True)

  addressee = relationship('Addressee', back_populates='italco_user')
  service_user = relationship('ServiceUser', back_populates='italco_user')
  delivery_group = relationship('DeliveryGroup', back_populates='italco_user')
  collection_point = relationship('CollectionPoint', back_populates='italco_user')

  def format_user(self, role: UserRole):
    if role == UserRole.ADMIN:
      return self.to_dict()
    else:
      return {
        'id': self.id,
        'email': self.email,
        'role': self.role.value
      }


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
  transport_delivery_group = relationship('TransportDeliveryGroup', back_populates='delivery_group')


class Transport(BaseEntity):
  __tablename__ = 'transport'

  name = Column(String, nullable=False)
  plate = Column(String, nullable=False)

  transport_delivery_group = relationship('TransportDeliveryGroup', back_populates='transport')


class TransportDeliveryGroup(BaseEntity):
  __tablename__ = 'transport_delivery_group'

  start = Column(Date, nullable=False)
  end = Column(Date, nullable=True)
  transport_id = Column(Integer, ForeignKey('transport.id'), nullable=False)
  delivery_group_id = Column(Integer, ForeignKey('delivery_group.id'), nullable=True)

  transport = relationship('Transport', back_populates='transport_delivery_group')
  delivery_group = relationship('DeliveryGroup', back_populates='transport_delivery_group')


class Order(BaseEntity):
  __tablename__ = 'order'

  status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
  type = Column(Enum(OrderType), nullable=False)
  dpc = Column(Date, nullable=False)
  drc = Column(Date, nullable=False)
  booking_date = Column(Date, nullable=True)
  assignament_date = Column(Date, nullable=True)
  customer_note = Column(String, nullable=True)
  operator_note = Column(String, nullable=True)
  motivation = Column(String, nullable=True)
  photo = Column(LargeBinary, nullable=True)
  photo_mime_type = Column(String, nullable=True)
  products = Column(ARRAY(String), default=[])
  addressee_id = Column(Integer, ForeignKey('addressee.id'), nullable=False)
  delivery_group_id = Column(Integer, ForeignKey('delivery_group.id'), nullable=True)
  collection_point_id = Column(Integer, ForeignKey('collection_point.id'), nullable=False)

  addressee = relationship('Addressee', back_populates='order')
  delivery_group = relationship('DeliveryGroup', back_populates='order')
  collection_point = relationship('CollectionPoint', back_populates='order')
  order_service_user = relationship('OrderServiceUser', back_populates='order')


class CollectionPoint(BaseEntity):
  __tablename__ = 'collection_point'

  name = Column(String, nullable=False)
  address = Column(String, nullable=False)
  city = Column(String, nullable=False)
  cap = Column(String, nullable=False)
  province = Column(String, nullable=False)
  user_id = Column(Integer, ForeignKey('italco_user.id'), nullable=False)

  order = relationship('Order', back_populates='collection_point')
  italco_user = relationship('ItalcoUser', back_populates='collection_point')


class Service(BaseEntity):
  __tablename__ = 'service'

  name = Column(String, nullable=False)
  description = Column(String, nullable=True)

  service_user = relationship('ServiceUser', back_populates='service')


class ServiceUser(BaseEntity):
  __tablename__ = 'service_user'

  price = Column(Float, nullable=False)
  user_id = Column(Integer, ForeignKey('italco_user.id'), nullable=False)
  service_id = Column(Integer, ForeignKey('service.id'), nullable=False)

  service = relationship('Service', back_populates='service_user')
  italco_user = relationship('ItalcoUser', back_populates='service_user')
  order_service_user = relationship('OrderServiceUser', back_populates='service_user')


class OrderServiceUser(BaseEntity):
  __tablename__ = 'order_service_user'

  order_id = Column(Integer, ForeignKey('order.id'), nullable=False)
  service_user_id = Column(Integer, ForeignKey('service_user.id'), nullable=False)

  order = relationship('Order', back_populates='order_service_user')
  service_user = relationship('ServiceUser', back_populates='order_service_user')
