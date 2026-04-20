from sqlalchemy.orm import relationship, Session, with_loader_criteria
from sqlalchemy import (
  Column,
  Enum,
  Date,
  String,
  Float,
  Integer,
  LargeBinary,
  ForeignKey,
  Boolean,
  Numeric,
  Time,
  event,
  inspect,
  JSON,
)

from database_api import BaseEntity
from .enum import UserRole, OrderStatus, OrderType, ScheduleType, EuronicsStatus, RaeStatus


class BaseItalcoEntity(BaseEntity):
  __abstract__ = True

  company_id = Column(Integer, ForeignKey('company.id'), nullable=False)


class Company(BaseEntity):
  __tablename__ = 'company'

  name = Column(String)

  log = relationship('Log', back_populates='company')
  users = relationship('User', back_populates='company')
  order = relationship('Order', back_populates='company')
  photo = relationship('Photo', back_populates='company')
  service = relationship('Service', back_populates='company')
  product = relationship('Product', back_populates='company')
  history = relationship('History', back_populates='company')
  schedule = relationship('Schedule', back_populates='company')
  transport = relationship('Transport', back_populates='company')
  constraint = relationship('Constraint', back_populates='company')
  motivation = relationship('Motivation', back_populates='company')
  rae_product = relationship('RaeProduct', back_populates='company')
  service_user = relationship('ServiceUser', back_populates='company')
  customer_rule = relationship('CustomerRule', back_populates='company')
  schedule_item = relationship('ScheduleItem', back_populates='company')
  customer_group = relationship('CustomerGroup', back_populates='company')
  delivery_group = relationship('DeliveryGroup', back_populates='company')
  geographic_code = relationship('GeographicCode', back_populates='company')
  geographic_zone = relationship('GeographicZone', back_populates='company')
  collection_point = relationship('CollectionPoint', back_populates='company')
  rae_product_group = relationship('RaeProductGroup', back_populates='company')
  delivery_user_info = relationship('DeliveryUserInfo', back_populates='company')
  customer_user_info = relationship('CustomerUserInfo', back_populates='company')
  schedule_item_order = relationship('ScheduleItemOrder', back_populates='company')
  schedule_item_collection_point = relationship('ScheduleItemCollectionPoint', back_populates='company')


class User(BaseItalcoEntity):
  __tablename__ = 'user'

  password = Column(String)
  role = Column(Enum(UserRole), nullable=False)
  nickname = Column(String, unique=True, nullable=False)
  customer_group_id = Column(Integer, ForeignKey('customer_group.id'), nullable=True)

  log = relationship('Log', back_populates='user')
  rae_product = relationship('RaeProduct', back_populates='user')
  service = relationship('Service', back_populates='user')
  company = relationship('Company', back_populates='users')
  customer_group = relationship('CustomerGroup', back_populates='user')
  delivery_group = relationship('DeliveryGroup', back_populates='user')
  delivery_user_info = relationship('DeliveryUserInfo', back_populates='user')
  customer_user_info = relationship('CustomerUserInfo', back_populates='user')
  service_user = relationship('ServiceUser', back_populates='user', cascade='all, delete-orphan')
  customer_rule = relationship('CustomerRule', back_populates='user', cascade='all, delete-orphan')
  collection_point = relationship('CollectionPoint', back_populates='user', cascade='all, delete-orphan')

  def format_user(self, role: UserRole):
    if role == UserRole.ADMIN:
      return self.to_dict()
    else:
      return {'id': self.id, 'nickname': self.nickname, 'role': self.role.value}


class DeliveryUserInfo(BaseItalcoEntity):
  __tablename__ = 'delivery_user_info'

  cap = Column(String)
  lat = Column(Numeric(11, 8))
  lon = Column(Numeric(11, 8))
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  user = relationship('User', back_populates='delivery_user_info')
  company = relationship('Company', back_populates='delivery_user_info')


class CustomerUserInfo(BaseItalcoEntity):
  __tablename__ = 'customer_user_info'

  city = Column(String)
  email = Column(String)
  address = Column(String)
  tax_code = Column(String)
  rae_code = Column(String)
  import_code = Column(String)
  company_name = Column(String)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  user = relationship('User', back_populates='customer_user_info')
  company = relationship('Company', back_populates='customer_user_info')


class CustomerGroup(BaseItalcoEntity):
  __tablename__ = 'customer_group'

  name = Column(String, nullable=False)

  user = relationship('User', back_populates='customer_group')
  company = relationship('Company', back_populates='customer_group')


class DeliveryGroup(BaseItalcoEntity):
  __tablename__ = 'delivery_group'

  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
  schedule_id = Column(Integer, ForeignKey('schedule.id'), nullable=False)

  user = relationship('User', back_populates='delivery_group')
  company = relationship('Company', back_populates='delivery_group')
  schedule = relationship('Schedule', back_populates='delivery_group')


class Transport(BaseItalcoEntity):
  __tablename__ = 'transport'

  cap = Column(String)
  name = Column(String, nullable=False)
  plate = Column(String, nullable=False)

  company = relationship('Company', back_populates='transport')
  schedule = relationship('Schedule', back_populates='transport')


class Order(BaseItalcoEntity):
  __tablename__ = 'order'

  status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.ACQUIRED)
  type = Column(Enum(OrderType), nullable=False)
  addressee = Column(String, nullable=False)
  address = Column(String, nullable=False)
  cap = Column(String, nullable=False)
  dpc = Column(Date, nullable=False)
  drc = Column(Date, nullable=False)
  anomaly = Column(Boolean, default=False)
  delay = Column(Boolean, default=False)
  confirmed = Column(Boolean, default=False)

  floor = Column(Integer)
  elevator = Column(Boolean)
  addressee_contact = Column(String)
  booking_date = Column(Date)
  confirmation_date = Column(Date)
  completion_date = Column(Date)
  customer_note = Column(String)
  operator_note = Column(String)
  signature = Column(LargeBinary)
  mark = Column(Float)

  external_link = Column(String)
  external_id = Column(String)
  external_status = Column(Enum(EuronicsStatus))

  company = relationship('Company', back_populates='order')
  schedule_item_order = relationship('ScheduleItemOrder', back_populates='order')
  photo = relationship('Photo', back_populates='order', cascade='all, delete-orphan')
  product = relationship('Product', back_populates='order', cascade='all, delete-orphan')
  histories = relationship('History', back_populates='order', cascade='all, delete-orphan')
  motivations = relationship('Motivation', back_populates='order', cascade='all, delete-orphan')


class History(BaseItalcoEntity):
  __tablename__ = 'history'

  status = Column(JSON, nullable=False)
  order_id = Column(Integer, ForeignKey('order.id'), nullable=False)

  order = relationship('Order', back_populates='histories')
  company = relationship('Company', back_populates='histories')


class Motivation(BaseItalcoEntity):
  __tablename__ = 'motivation'

  text = Column(String)
  delay = Column(Boolean, default=False)
  anomaly = Column(Boolean, default=False)
  status = Column(Enum(OrderStatus), nullable=False)
  order_id = Column(Integer, ForeignKey('order.id'), nullable=False)

  order = relationship('Order', back_populates='motivations')
  company = relationship('Company', back_populates='motivations')


class Schedule(BaseItalcoEntity):
  __tablename__ = 'schedule'

  date = Column(Date, nullable=False)
  transport_id = Column(Integer, ForeignKey('transport.id'), nullable=False)

  company = relationship('Company', back_populates='schedule')
  transport = relationship('Transport', back_populates='schedule')
  schedule_item = relationship('ScheduleItem', back_populates='schedule')
  delivery_group = relationship('DeliveryGroup', back_populates='schedule')


class ScheduleItem(BaseItalcoEntity):
  __tablename__ = 'schedule_item'

  index = Column(Integer)
  completed = Column(Boolean, default=False)
  end_time_slot = Column(Time)
  start_time_slot = Column(Time)
  operation_type = Column(Enum(ScheduleType))
  schedule_id = Column(ForeignKey('schedule.id'), nullable=False)

  company = relationship('Company', back_populates='schedule_item')
  schedule = relationship('Schedule', back_populates='schedule_item')
  schedule_item_order = relationship('ScheduleItemOrder', back_populates='schedule_item')
  schedule_item_collection_point = relationship('ScheduleItemCollectionPoint', back_populates='schedule_item')


class ScheduleItemOrder(BaseItalcoEntity):
  __tablename__ = 'schedule_item_order'

  order_id = Column(ForeignKey('order.id'), nullable=False)
  schedule_item_id = Column(ForeignKey('schedule_item.id'), nullable=False)

  order = relationship('Order', back_populates='schedule_item_order')
  company = relationship('Company', back_populates='schedule_item_order')
  schedule_item = relationship('ScheduleItem', back_populates='schedule_item_order')


class ScheduleItemCollectionPoint(BaseItalcoEntity):
  __tablename__ = 'schedule_item_collection_point'

  schedule_item_id = Column(ForeignKey('schedule_item.id'), nullable=False)
  collection_point_id = Column(ForeignKey('collection_point.id'), nullable=False)

  company = relationship('Company', back_populates='schedule_item_collection_point')
  schedule_item = relationship('ScheduleItem', back_populates='schedule_item_collection_point')
  collection_point = relationship('CollectionPoint', back_populates='schedule_item_collection_point')


class Photo(BaseItalcoEntity):
  __tablename__ = 'photo'

  link = Column(String, nullable=False)
  order_id = Column(Integer, ForeignKey('order.id'), nullable=False)

  order = relationship('Order', back_populates='photo')
  company = relationship('Company', back_populates='photo')


class CollectionPoint(BaseItalcoEntity):
  __tablename__ = 'collection_point'

  opening_time = Column(Time)
  closing_time = Column(Time)
  cap = Column(String, nullable=False)
  name = Column(String, nullable=False)
  address = Column(String, nullable=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  user = relationship('User', back_populates='collection_point')
  company = relationship('Company', back_populates='collection_point')
  product = relationship('Product', back_populates='collection_point')
  schedule_item_collection_point = relationship('ScheduleItemCollectionPoint', back_populates='collection_point')


class Service(BaseItalcoEntity):
  __tablename__ = 'service'

  duration = Column(Integer)
  description = Column(String)
  max_services = Column(Integer)
  name = Column(String, nullable=False)
  type = Column(Enum(OrderType), nullable=False)
  professional = Column(Boolean, default=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  user = relationship('User', back_populates='service')
  company = relationship('Company', back_populates='service')
  service_user = relationship('ServiceUser', back_populates='service')


class ServiceUser(BaseItalcoEntity):
  __tablename__ = 'service_user'

  code = Column(String)
  price = Column(Float, nullable=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
  service_id = Column(Integer, ForeignKey('service.id'), nullable=False)

  user = relationship('User', back_populates='service_user')
  company = relationship('Company', back_populates='service_user')
  service = relationship('Service', back_populates='service_user')
  product = relationship('Product', back_populates='service_user')


class Product(BaseItalcoEntity):
  __tablename__ = 'product'

  name = Column(String, nullable=False)
  order_id = Column(Integer, ForeignKey('order.id'), nullable=False)
  rae_product_id = Column(Integer, ForeignKey('rae_product.id'), nullable=True)
  service_user_id = Column(Integer, ForeignKey('service_user.id'), nullable=False)
  collection_point_id = Column(Integer, ForeignKey('collection_point.id'), nullable=False)

  order = relationship('Order', back_populates='product')
  company = relationship('Company', back_populates='product')
  rae_product = relationship('RaeProduct', back_populates='product')
  service_user = relationship('ServiceUser', back_populates='product')
  collection_point = relationship('CollectionPoint', back_populates='product')


class RaeProduct(BaseItalcoEntity):
  __tablename__ = 'rae_product'

  quantity = Column(Integer, default=1)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
  status = Column(Enum(RaeStatus), nullable=False, default=RaeStatus.GENERATED)
  rae_product_group_id = Column(Integer, ForeignKey('rae_product_group.id'), nullable=False)

  user = relationship('User', back_populates='rae_product')
  company = relationship('Company', back_populates='rae_product')
  product = relationship('Product', back_populates='rae_product')
  rae_product_group = relationship('RaeProductGroup', back_populates='rae_product')


class RaeProductGroup(BaseItalcoEntity):
  __tablename__ = 'rae_product_group'

  name = Column(String, nullable=False)
  cer_code = Column(Integer, nullable=False)
  group_code = Column(String, nullable=False)

  company = relationship('Company', back_populates='rae_product_group')
  rae_product = relationship('RaeProduct', back_populates='rae_product_group')


class GeographicZone(BaseItalcoEntity):
  __tablename__ = 'geographic_zone'

  name = Column(String, nullable=False)

  company = relationship('Company', back_populates='zone')
  constraints = relationship('Constraint', back_populates='zone', cascade='all, delete-orphan')
  geographic_codes = relationship('GeographicCode', back_populates='zone', cascade='all, delete-orphan')


class GeographicCode(BaseItalcoEntity):
  __tablename__ = 'geographic_code'

  zone_id = Column(Integer, ForeignKey('geographic_zone.id'), nullable=False)
  code = Column(String, nullable=False)
  type = Column(Boolean, nullable=False)

  company = relationship('Company', back_populates='geographic_codes')
  zone = relationship('GeographicZone', back_populates='geographic_codes')


class Constraint(BaseItalcoEntity):
  __tablename__ = 'constraints'

  zone_id = Column(Integer, ForeignKey('geographic_zone.id'), nullable=False)
  day_of_week = Column(Integer, nullable=False)
  max_orders = Column(Integer, nullable=False)

  company = relationship('Company', back_populates='constraints')
  zone = relationship('GeographicZone', back_populates='constraints')


class CustomerRule(BaseItalcoEntity):
  __tablename__ = 'customer_rule'

  day_of_week = Column(Integer, nullable=False)
  max_orders = Column(Integer, nullable=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  user = relationship('User', back_populates='customer_rule')
  company = relationship('Company', back_populates='customer_rule')


class Chatty(BaseEntity):
  __tablename__ = 'chatty'

  thread_id = Column(String, nullable=False)


class Log(BaseItalcoEntity):
  __tablename__ = 'log'

  content = Column(String, nullable=False)
  user_id = Column(Integer, ForeignKey('user.id'), nullable=False)

  user = relationship('User', back_populates='log')
  company = relationship('Company', back_populates='log')


@event.listens_for(Session, 'before_flush')
def track_order_history(session: Session, flush_context, instances):
  for obj in session.new:
    if isinstance(obj, Order):
      session.add(
        History(
          order=obj,
          status={
            'type': 'status',
            'value': obj.status.value if obj.status else None,
          },
        )
      )

  for obj in session.dirty:
    if isinstance(obj, Order):
      state = inspect(obj)
      for field in ['status', 'anomaly', 'delay', 'confirmed']:
        if state.attrs[field].history.has_changes():
          value = getattr(obj, field)
          if field == 'status' and value:
            value = value.value

          session.add(
            History(
              order=obj,
              status={
                'type': field,
                'value': value,
              },
            )
          )


@event.listens_for(Session, "do_orm_execute")
def add_company_filter(execute_state):
    if not execute_state.is_select:
        return
      
    company_id = execute_state.session.info.get("company_id")
    if not company_id:
        return

    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            BaseItalcoEntity,
            lambda cls: cls.company_id == company_id,
            include_aliases=True
        )
    )
