from io import BytesIO
from xhtml2pdf import pisa
from flask import Blueprint, render_template, make_response, request

from database_api import Session
from ..database.enum import UserRole
from .order import query_orders, format_query_result
from . import error_catching_decorator, flask_session_authentication
from ..database.schema import Schedule, ItalcoUser, Order, DeliveryGroup, Transport, OrderServiceUser, ServiceUser, Service, CollectionPoint, Photo


export_bp = Blueprint('export_bp', __name__)


@export_bp.route('order/<id>', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR])
def export_order_report(user: ItalcoUser, id):
  orders = []
  for tupla in query_orders(user, [{
    'model': 'Order',
    'field': 'id',
    'value': int(id)
  }]):
    orders = format_query_result(tupla, orders, user)
  if len(orders) != 1:
    raise Exception('Numero di ordini trovati non valido')

  result = BytesIO()
  pisa_status = pisa.CreatePDF(src=render_template(
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
    note=orders[0].get('customer_note', '/')
  ), dest=result)
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  response = make_response(result.getvalue())
  response.headers['Content-Type'] = 'application/pdf'
  response.headers['Content-Disposition'] = 'inline; filename=report.pdf'
  return response


@export_bp.route('invoice', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def export_orders_invoice(user: ItalcoUser):
  orders = []
  for tupla in query_orders(user, request.json['filters'], request.json['date_filter']):
    orders = format_query_result(tupla, orders, user)
    
  if len(orders) == 0:
    raise Exception('Numero di ordini trovati non valido')
  
  result = BytesIO()
  pisa_status = pisa.CreatePDF(src=render_template(
    'orders_invoice.html',
    orders=orders,
    total=sum([order['price'] for order in orders]),
    end_date=request.json['date_filter']['end_date'],
    start_date=request.json['date_filter']['start_date'],
    customer=orders[0]['user']['email'] if orders else None
  ), dest=result)
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  response = make_response(result.getvalue())
  response.headers['Content-Type'] = 'application/pdf'
  response.headers['Content-Disposition'] = 'inline; filename=report.pdf'
  return response


@export_bp.route('schedule/<id>', methods=['GET'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def export_orders_schedule(user: ItalcoUser, id):
  orders = []
  schedule = {}
  for index, tupla in enumerate(query_schedule(id)):
    if index == 0:
      schedule = {
        **tupla[0].to_dict(),
        'transport': tupla[2].to_dict(),
        'delivery_group': tupla[1].to_dict()
      }
    orders = format_query_result(tuple(
      value for index, value in enumerate(tupla) if not index in [0, 1, 2]
    ), orders, user) 
  
  result = BytesIO()
  pisa_status = pisa.CreatePDF(src=render_template(
    'schedules_report.html',
    id=schedule['id'],
    date=schedule['date'],
    delivery_group=schedule['delivery_group']['name'],
    transport=schedule['transport']['name'],
    orders=orders
  ), dest=result)
  if pisa_status.err:
    raise Exception('Errore nella creazione del PDF')

  response = make_response(result.getvalue())
  response.headers['Content-Type'] = 'application/pdf'
  response.headers['Content-Disposition'] = 'inline; filename=report.pdf'
  return response


def query_schedule(id: int) -> list[tuple[Schedule, DeliveryGroup, Transport, Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo]]:
  with Session() as session:
    return session.query(
      Schedule, DeliveryGroup, Transport, Order, OrderServiceUser, ServiceUser, Service, ItalcoUser, CollectionPoint, Photo
    ).join(
      DeliveryGroup, Schedule.delivery_group_id == DeliveryGroup.id
    ).join(
      Transport, Schedule.transport_id == Transport.id
    ).outerjoin(
      Order, Order.schedule_id == Schedule.id
    ).outerjoin(
      CollectionPoint, Order.collection_point_id == CollectionPoint.id
    ).outerjoin(
      OrderServiceUser, OrderServiceUser.order_id == Order.id
    ).outerjoin(
      ServiceUser, OrderServiceUser.service_user_id == ServiceUser.id
    ).outerjoin(
      Service, ServiceUser.service_id == Service.id
    ).outerjoin(
      ItalcoUser, ServiceUser.user_id == ItalcoUser.id
    ).outerjoin(
      Photo, Photo.order_id == Order.id
    ).filter(
      Schedule.id == id
    ).all()
