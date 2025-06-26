from flask import Blueprint, request

from database_api import Session
from ..database.enum import UserRole
from api import error_catching_decorator
from . import flask_session_authentication
from ..database.schema import CustomerRule, ItalcoUser
from database_api.operations import create, delete, get_by_id


customer_rules_bp = Blueprint('customer_rules_bp', __name__)


@customer_rules_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def create_customer_rules(user: ItalcoUser):
  return {
    'status': 'ok',
    'customer_rules': create(CustomerRule, request.json).to_dict()
  }


@customer_rules_bp.route('', methods=['DELETE'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def delete_customer_rules(user: ItalcoUser):
  for id in request.json['ids']:
    delete(get_by_id(CustomerRule, int(id)))
  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


@customer_rules_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def get_customer_rules(user: ItalcoUser):
  customer_rules = []
  for tupla in query_customer_rules():
    customer_rules = format_query_result(tupla, customer_rules)

  return {
    'status': 'ok',
    'customer_rules': customer_rules
  }


@customer_rules_bp.route('', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.CUSTOMER])
def get_my_customer_rules(user: ItalcoUser):
  return {
    'status': 'ok',
    'customer_rules': [rule.to_dict() for rule in query_my_customer_rules(user)]
  }


def query_customer_rules() -> list[CustomerRule, ItalcoUser]:
  with Session() as session:
    return session.query(
      CustomerRule, ItalcoUser
    ).join(
      ItalcoUser, ItalcoUser.id == CustomerRule.user_id
    ).all()


def query_my_customer_rules(user: ItalcoUser) -> list[CustomerRule]:
  with Session() as session:
    return session.query(
      CustomerRule
    ).filter(
      CustomerRule.user_id == user.id
    ).all()


def format_query_result(tupla: tuple[CustomerRule, ItalcoUser], list: list[dict]) -> list[dict]:
  for element in list:
    if element['id'] == tupla[1].id:
      element['rules'].append(tupla[0].to_dict())
      return list

  list.append({
    **tupla[1].to_dict(),
    'rules': [tupla[0].to_dict()]
  })
  return list
