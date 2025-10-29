from sqlalchemy.orm import relationship
from sqlalchemy import Column, Enum, Date, String, Float, Integer, LargeBinary, ForeignKey, Boolean, Numeric, Time

from database_api import BaseEntity
from .enum import UserRole, OrderStatus, OrderType


class User(BaseEntity):
  __tablename__ = 'user'

  email = Column(String)
  password = Column(String)
  lat = Column(Numeric(11, 8))
  lon = Column(Numeric(11, 8))
  role = Column(Enum(UserRole), nullable=False)
  nickname = Column(String, unique=True, nullable=False)
  customer_group_id = Column(Integer, ForeignKey('customer_group.id'), nullable=True)

  customer_group = relationship('CustomerGroup', back_populates='user')
  delivery_group = relationship('DeliveryGroup', back_populates='user')
  service_user = relationship('ServiceUser', back_populates='user', cascade='all, delete-orphan')
  customer_rule = relationship('CustomerRule', back_populates='user', cascade='all, delete-orphan')
  collection_point = relationship('CollectionPoint', back_populates='user', cascade='all, delete-orphan')

  def format_user(self, role: UserRole):
    if role == UserRole.ADMIN:
      return self.to_dict()
    else:
      return {'id': self.id, 'nickname': self.nickname, 'role': self.role.value}


class CustomerGroup(BaseEntity):
  __tablename__ = 'customer_group'

  name = Column(String, nullable=False)

  user = relationship('User', back_populates='customer_group')


class DeliveryGroup(BaseEntity):
  __tablename__ = 'delivery_group'

  schedule_id = Column(Integer, ForeignKey('schedule.id'), nullable=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  schedule = relationship('Schedule', back_populates='delivery_group')
  user = relationship('User', back_populates='delivery_group')


class Transport(BaseEntity):
  __tablename__ = 'transport'

  name = Column(String, nullable=False)
  plate = Column(String, nullable=False)

  schedule = relationship('Schedule', back_populates='transport')


class Order(BaseEntity):
  __tablename__ = 'order'

  status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
  type = Column(Enum(OrderType), nullable=False)
  addressee = Column(String, nullable=False)
  address = Column(String, nullable=False)
  addressee_contact = Column(String, nullable=True)
  cap = Column(String, nullable=False)
  dpc = Column(Date, nullable=False)
  drc = Column(Date, nullable=False)
  booking_date = Column(Date, nullable=True)
  assignament_date = Column(Date, nullable=True)
  customer_note = Column(String, nullable=True)
  operator_note = Column(String, nullable=True)
  schedule_id = Column(Integer, ForeignKey('schedule.id'), nullable=True)
  collection_point_id = Column(Integer, ForeignKey('collection_point.id'), nullable=False)
  schedule_index = Column(Integer, nullable=True)
  start_time_slot = Column(Time, nullable=True)
  end_time_slot = Column(Time, nullable=True)
  anomaly = Column(Boolean, nullable=True, default=False)
  delay = Column(Boolean, nullable=True, default=False)
  signature = Column(LargeBinary, nullable=True)
  id_cloned_order = Column(Integer, nullable=True)

  photo = relationship('Photo', back_populates='order')
  schedule = relationship('Schedule', back_populates='order')
  collection_point = relationship('CollectionPoint', back_populates='order')
  order_service_user = relationship('OrderServiceUser', back_populates='order')
  motivations = relationship('Motivation', back_populates='order', cascade='all, delete-orphan')


class Motivation(BaseEntity):
  __tablename__ = 'motivation'

  id_order = Column(Integer, ForeignKey('order.id'), nullable=False)
  status = Column(Enum(OrderStatus), nullable=False)
  delay = Column(Boolean, nullable=True, default=False)
  anomaly = Column(Boolean, nullable=True, default=False)
  text = Column(String, nullable=True)

  order = relationship('Order', back_populates='motivations')


class Schedule(BaseEntity):
  __tablename__ = 'schedule'

  date = Column(Date, nullable=False)
  transport_id = Column(Integer, ForeignKey('transport.id'), nullable=False)

  order = relationship('Order', back_populates='schedule')
  transport = relationship('Transport', back_populates='schedule')
  delivery_group = relationship('DeliveryGroup', back_populates='schedule')


class Photo(BaseEntity):
  __tablename__ = 'photo'

  photo = Column(LargeBinary, nullable=False)
  mime_type = Column(String, nullable=False)
  order_id = Column(Integer, ForeignKey('order.id'), nullable=False)

  order = relationship('Order', back_populates='photo')


class CollectionPoint(BaseEntity):
  __tablename__ = 'collection_point'

  name = Column(String, nullable=False)
  address = Column(String, nullable=False)
  cap = Column(String, nullable=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  order = relationship('Order', back_populates='collection_point')
  user = relationship('User', back_populates='collection_point')


class Service(BaseEntity):
  __tablename__ = 'service'

  name = Column(String, nullable=False)
  type = Column(Enum(OrderType), nullable=False)
  description = Column(String, nullable=True)
  max_services = Column(Integer, nullable=True)

  service_user = relationship('ServiceUser', back_populates='service')


class ServiceUser(BaseEntity):
  __tablename__ = 'service_user'

  price = Column(Float, nullable=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
  service_id = Column(Integer, ForeignKey('service.id'), nullable=False)

  service = relationship('Service', back_populates='service_user')
  user = relationship('User', back_populates='service_user')
  order_service_user = relationship('OrderServiceUser', back_populates='service_user')


class OrderServiceUser(BaseEntity):
  __tablename__ = 'order_service_user'

  order_id = Column(Integer, ForeignKey('order.id'), nullable=False)
  product = Column(String, nullable=False)
  service_user_id = Column(Integer, ForeignKey('service_user.id'), nullable=False)

  order = relationship('Order', back_populates='order_service_user')
  service_user = relationship('ServiceUser', back_populates='order_service_user')


class GeographicZone(BaseEntity):
  __tablename__ = 'geographic_zone'

  name = Column(String, nullable=False)

  constraints = relationship('Constraint', back_populates='zone', cascade='all, delete-orphan')
  geographic_codes = relationship('GeographicCode', back_populates='zone', cascade='all, delete-orphan')


class GeographicCode(BaseEntity):
  __tablename__ = 'geographic_code'

  zone_id = Column(Integer, ForeignKey('geographic_zone.id'), nullable=False)
  code = Column(String, nullable=False)
  type = Column(Boolean, nullable=False)

  zone = relationship('GeographicZone', back_populates='geographic_codes')


class Constraint(BaseEntity):
  __tablename__ = 'constraints'

  zone_id = Column(Integer, ForeignKey('geographic_zone.id'), nullable=False)
  day_of_week = Column(Integer, nullable=False)
  max_orders = Column(Integer, nullable=False)

  zone = relationship('GeographicZone', back_populates='constraints')


class CustomerRule(BaseEntity):
  __tablename__ = 'customer_rule'

  day_of_week = Column(Integer, nullable=False)
  max_orders = Column(Integer, nullable=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  user = relationship('User', back_populates='customer_rule')


class Chatty(BaseEntity):
  __tablename__ = 'chatty'

  thread_id = Column(String, nullable=False)
