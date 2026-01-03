from sqlalchemy.orm import relationship
from sqlalchemy import Column, Enum, Date, String, Float, Integer, LargeBinary, ForeignKey, Boolean, Numeric, Time

from database_api import BaseEntity
from .enum import UserRole, OrderStatus, OrderType, ScheduleType


class User(BaseEntity):
  __tablename__ = 'user'

  email = Column(String)
  password = Column(String)
  role = Column(Enum(UserRole), nullable=False)
  nickname = Column(String, unique=True, nullable=False)
  customer_group_id = Column(Integer, ForeignKey('customer_group.id'), nullable=True)

  customer_group = relationship('CustomerGroup', back_populates='user')
  delivery_group = relationship('DeliveryGroup', back_populates='user')
  delivery_user_info = relationship('DeliveryUserInfo', back_populates='user')
  service_user = relationship('ServiceUser', back_populates='user', cascade='all, delete-orphan')
  customer_rule = relationship('CustomerRule', back_populates='user', cascade='all, delete-orphan')
  collection_point = relationship('CollectionPoint', back_populates='user', cascade='all, delete-orphan')

  def format_user(self, role: UserRole):
    if role == UserRole.ADMIN:
      return self.to_dict()
    else:
      return {'id': self.id, 'nickname': self.nickname, 'role': self.role.value}


class DeliveryUserInfo(BaseEntity):
  __tablename__ = 'delivery_user_info'

  cap = Column(String)
  lat = Column(Numeric(11, 8))
  lon = Column(Numeric(11, 8))
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  user = relationship('User', back_populates='delivery_user_info')


class CustomerGroup(BaseEntity):
  __tablename__ = 'customer_group'

  name = Column(String, nullable=False)

  user = relationship('User', back_populates='customer_group')


class DeliveryGroup(BaseEntity):
  __tablename__ = 'delivery_group'

  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
  schedule_id = Column(Integer, ForeignKey('schedule.id'), nullable=False)

  user = relationship('User', back_populates='delivery_group')
  schedule = relationship('Schedule', back_populates='delivery_group')


class Transport(BaseEntity):
  __tablename__ = 'transport'

  cap = Column(String)
  name = Column(String, nullable=False)
  plate = Column(String, nullable=False)

  schedule = relationship('Schedule', back_populates='transport')


class Order(BaseEntity):
  __tablename__ = 'order'

  status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
  type = Column(Enum(OrderType), nullable=False)
  addressee = Column(String, nullable=False)
  address = Column(String, nullable=False)
  cap = Column(String, nullable=False)
  dpc = Column(Date, nullable=False)
  drc = Column(Date, nullable=False)
  anomaly = Column(Boolean, default=False)
  delay = Column(Boolean, default=False)

  floor = Column(Integer)
  elevator = Column(Boolean)
  addressee_contact = Column(String)
  booking_date = Column(Date)
  assignament_date = Column(Date)
  customer_note = Column(String)
  operator_note = Column(String)
  signature = Column(LargeBinary)
  mark = Column(Float)
  external_id = Column(String)

  photo = relationship('Photo', back_populates='order')
  schedule_item_order = relationship('ScheduleItemOrder', back_populates='order')
  product = relationship('Product', back_populates='order', cascade='all, delete-orphan')
  motivations = relationship('Motivation', back_populates='order', cascade='all, delete-orphan')


class Motivation(BaseEntity):
  __tablename__ = 'motivation'

  id_order = Column(Integer, ForeignKey('order.id'), nullable=False)
  status = Column(Enum(OrderStatus), nullable=False)
  delay = Column(Boolean, default=False)
  anomaly = Column(Boolean, default=False)
  text = Column(String)

  order = relationship('Order', back_populates='motivations')


class Schedule(BaseEntity):
  __tablename__ = 'schedule'

  date = Column(Date, nullable=False)
  transport_id = Column(Integer, ForeignKey('transport.id'), nullable=False)

  transport = relationship('Transport', back_populates='schedule')
  schedule_item = relationship('ScheduleItem', back_populates='schedule')
  delivery_group = relationship('DeliveryGroup', back_populates='schedule')


class ScheduleItem(BaseEntity):
  __tablename__ = 'schedule_item'

  index = Column(Integer)
  end_time_slot = Column(Time)
  start_time_slot = Column(Time)
  operation_type = Column(Enum(ScheduleType))
  schedule_id = Column(ForeignKey('schedule.id'), nullable=False)

  schedule = relationship('Schedule', back_populates='schedule_item')
  schedule_item_order = relationship('ScheduleItemOrder', back_populates='schedule_item')
  schedule_item_collection_point = relationship('ScheduleItemCollectionPoint', back_populates='schedule_item')


class ScheduleItemOrder(BaseEntity):
  __tablename__ = 'schedule_item_order'

  order_id = Column(ForeignKey('order.id'), nullable=False)
  schedule_item_id = Column(ForeignKey('schedule_item.id'), nullable=False)

  order = relationship('Order', back_populates='schedule_item_order')
  schedule_item = relationship('ScheduleItem', back_populates='schedule_item_order')


class ScheduleItemCollectionPoint(BaseEntity):
  __tablename__ = 'schedule_item_collection_point'

  schedule_item_id = Column(ForeignKey('schedule_item.id'), nullable=False)
  collection_point_id = Column(ForeignKey('collection_point.id'), nullable=False)

  schedule_item = relationship('ScheduleItem', back_populates='schedule_item_collection_point')
  collection_point = relationship('CollectionPoint', back_populates='schedule_item_collection_point')


class Photo(BaseEntity):
  __tablename__ = 'photo'

  link = Column(String, nullable=False)
  order_id = Column(Integer, ForeignKey('order.id'), nullable=False)

  order = relationship('Order', back_populates='photo')


class CollectionPoint(BaseEntity):
  __tablename__ = 'collection_point'

  opening_time = Column(Time)
  closing_time = Column(Time)
  cap = Column(String, nullable=False)
  name = Column(String, nullable=False)
  address = Column(String, nullable=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  user = relationship('User', back_populates='collection_point')
  product = relationship('Product', back_populates='collection_point')
  schedule_item_collection_point = relationship('ScheduleItemCollectionPoint', back_populates='collection_point')


class Service(BaseEntity):
  __tablename__ = 'service'

  name = Column(String, nullable=False)
  type = Column(Enum(OrderType), nullable=False)
  description = Column(String)
  max_services = Column(Integer)
  duration = Column(Integer)

  service_user = relationship('ServiceUser', back_populates='service')


class ServiceUser(BaseEntity):
  __tablename__ = 'service_user'

  code = Column(String)
  price = Column(Float, nullable=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
  service_id = Column(Integer, ForeignKey('service.id'), nullable=False)

  user = relationship('User', back_populates='service_user')
  service = relationship('Service', back_populates='service_user')
  product = relationship('Product', back_populates='service_user')


class Product(BaseEntity):
  __tablename__ = 'product'

  name = Column(String, nullable=False)
  order_id = Column(Integer, ForeignKey('order.id'), nullable=False)
  service_user_id = Column(Integer, ForeignKey('service_user.id'), nullable=False)
  collection_point_id = Column(Integer, ForeignKey('collection_point.id'), nullable=False)

  order = relationship('Order', back_populates='product')
  service_user = relationship('ServiceUser', back_populates='product')
  collection_point = relationship('CollectionPoint', back_populates='product')


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
