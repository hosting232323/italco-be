import base64
from io import BytesIO
from xhtml2pdf import pisa
from flask import Blueprint, render_template, make_response, request

from database_api import Session
from database_api.operations import get_by_id
from ..database.enum import UserRole, OrderStatus
from .users.session import flask_session_authentication
from .orders.queries import query_orders, format_query_result
from ..database.schema import (
  Schedule,
  User,
  Order,
  DeliveryGroup,
  Transport,
  OrderServiceUser,
  ServiceUser,
  Service,
  CollectionPoint,
)


export_bp = Blueprint('export_bp', __name__)


@export_bp.route('order/<id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR, UserRole.CUSTOMER])
def export_order_report(user: User, id):
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'id', 'value': int(id)}]):
    orders = format_query_result(tupla, orders, user)
  if len(orders) != 1:
    raise Exception('Numero di ordini trovati non valido')

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'order_report.html',
      id=orders[0]['id'],
      dpc=orders[0]['dpc'],
      drc=orders[0]['drc'],
      booking_date=orders[0].get('booking_date', '/'),
      customer=orders[0]['user'],
      address=orders[0]['address'],
      addressee=orders[0]['addressee'],
      addressee_contact=orders[0].get('addressee_contact', '/'),
      products=orders[0]['products'],
      collection_point=orders[0]['collection_point'],
      note=orders[0].get('customer_note', '/'),
      signature=get_signature(get_by_id(Order, orders[0]['id'])),
    ),
    dest=result,
  )
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  return export_pdf(result.getvalue())


@export_bp.route('invoice', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def export_orders_invoice(user: User):
  orders = []
  for tupla in query_orders(
    user,
    request.json['filters'] + [{'model': 'Order', 'field': 'status', 'value': OrderStatus.COMPLETED}],
  ):
    orders = format_query_result(tupla, orders, user)

  if len(orders) == 0:
    raise Exception('Numero di ordini trovati non valido')

  for filter in request.json['filters']:
    if filter['field'] == 'booking_date' and filter['model'] == 'Order':
      start_date = filter['value'][0]
      end_date = filter['value'][1]
      break

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'orders_invoice.html',
      orders=orders,
      end_date=start_date,
      start_date=end_date,
      total=sum([order['price'] for order in orders]),
      customer=orders[0]['user']['nickname'] if orders else None,
    ),
    dest=result,
  )
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  return export_pdf(result.getvalue())


@export_bp.route('schedule/<id>', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_orders_schedule(user: User, id):
  schedule = {}
  orders_dict = {}
  for index, tupla in enumerate(query_schedule(id)):
    if index == 0:
      schedule = {**tupla[0].to_dict(), 'transport': tupla[2].to_dict(), 'delivery_group': tupla[1].to_dict()}

    order_dict = format_query_result(
      tuple(value for index, value in enumerate(tupla) if index not in [0, 1, 2]), [], user
    )[0]
    if order_dict['id'] in orders_dict:
      for pname, services in order_dict['products'].items():
        if pname not in orders_dict[order_dict['id']]['products']:
          orders_dict[order_dict['id']]['products'][pname] = []
        orders_dict[order_dict['id']]['products'][pname].extend(services)
    else:
      order_dict['signature'] = get_signature(get_by_id(Order, order_dict['id']))
      orders_dict[order_dict['id']] = order_dict

  result = BytesIO()
  pisa_status = pisa.CreatePDF(
    src=render_template(
      'schedules_report.html',
      id=schedule['id'],
      date=schedule['date'],
      delivery_group=schedule['delivery_group']['name'],
      transport=schedule['transport']['name'],
      orders=list(orders_dict.values()),
    ),
    dest=result,
  )
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  return export_pdf(result.getvalue())


def get_signature(order: Order):
  if order.signature:
    signature_base64 = base64.b64encode(order.signature).decode('utf-8')
    return f'data:image/png;base64,{signature_base64}'
  else:
    return None


def export_pdf(document):
  response = make_response(document)
  response.headers['Content-Type'] = 'application/pdf'
  response.headers['Content-Disposition'] = 'inline; filename=report.pdf'
  return response


def query_schedule(
  id: int,
) -> list[
  tuple[Schedule, DeliveryGroup, Transport, Order, OrderServiceUser, ServiceUser, Service, User, CollectionPoint]
]:
  with Session() as session:
    return (
      session.query(
        Schedule, DeliveryGroup, Transport, Order, OrderServiceUser, ServiceUser, Service, User, CollectionPoint
      )
      .join(DeliveryGroup, Schedule.delivery_group_id == DeliveryGroup.id)
      .join(Transport, Schedule.transport_id == Transport.id)
      .outerjoin(Order, Order.schedule_id == Schedule.id)
      .outerjoin(CollectionPoint, Order.collection_point_id == CollectionPoint.id)
      .outerjoin(OrderServiceUser, OrderServiceUser.order_id == Order.id)
      .outerjoin(ServiceUser, OrderServiceUser.service_user_id == ServiceUser.id)
      .outerjoin(Service, ServiceUser.service_id == Service.id)
      .outerjoin(User, ServiceUser.user_id == User.id)
      .filter(Schedule.id == id)
      .all()
    )
