from sqlalchemy import and_
from flask import Blueprint, request
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from database_api import Session
from ..database.enum import UserRole
from .users.session import flask_session_authentication
from database_api.operations import create, delete, get_by_id
from ..database.schema import CustomerRule, User, Order, Product, ServiceUser


customer_rules_bp = Blueprint('customer_rules_bp', __name__)


@customer_rules_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_customer_rules(user: User):
  if request.json['day_of_week'] not in list(range(7)):
    raise ValueError('Invalid day_of_week value')

  return {'status': 'ok', 'customer_rules': create(CustomerRule, request.json).to_dict()}


@customer_rules_bp.route('', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def delete_customer_rules(user: User):
  for id in request.json['ids']:
    delete(get_by_id(CustomerRule, int(id)))
  return {'status': 'ok', 'message': 'Operazione completata'}


@customer_rules_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN])
def get_customer_rules(user: User):
  customer_rules = []
  for tupla in query_customer_rules():
    customer_rules = format_query_result(tupla, customer_rules)

  return {'status': 'ok', 'customer_rules': customer_rules}


@customer_rules_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.CUSTOMER])
def get_my_customer_rules(user: User):
  return {'status': 'ok', 'customer_rules': [rule.to_dict() for rule in query_my_customer_rules(user)]}


def check_customer_rules(user: User) -> list[datetime]:
  my_orders = query_my_orders(user)
  customer_rules = query_my_customer_rules(user)
  rule_days = [rule.day_of_week for rule in customer_rules]
  start = datetime.today().date()
  allowed_dates = []
  end = start + relativedelta(months=2)
  while start <= end:
    if start.weekday() not in rule_days:
      allowed_dates.append(start.strftime('%Y-%m-%d'))
    else:
      order_count = 0
      for order in my_orders:
        if order.dpc == start:
          order_count += 1
      for rule in customer_rules:
        if rule.day_of_week == start.weekday() and order_count < rule.max_orders:
          allowed_dates.append(start.strftime('%Y-%m-%d'))
          break
    start += timedelta(days=1)
  return allowed_dates


def query_customer_rules() -> list[CustomerRule, User]:
  with Session() as session:
    return session.query(CustomerRule, User).join(User, User.id == CustomerRule.user_id).all()


def query_my_customer_rules(user: User) -> list[CustomerRule]:
  with Session() as session:
    return session.query(CustomerRule).filter(CustomerRule.user_id == user.id).all()


def query_my_orders(user: User) -> list[Order]:
  with Session() as session:
    return (
      session.query(Order)
      .join(Product, Product.order_id == Order.id)
      .join(
        ServiceUser,
        and_(
          ServiceUser.id == Product.service_user_id,
          ServiceUser.user_id == user.id,
          Order.dpc > datetime.today(),
          Order.dpc < datetime.today() + relativedelta(months=2),
        ),
      )
      .all()
    )


def format_query_result(tupla: tuple[CustomerRule, User], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[1].id:
      element['rules'].append(tupla[0].to_dict())
      return list

  list.append({**tupla[1].to_dict(), 'rules': [tupla[0].to_dict()]})
  return list
