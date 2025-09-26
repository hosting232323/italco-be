import pandas as pd
from flask import Blueprint, request

from database_api import Session
from . import flask_session_authentication
from database_api.operations import create
from ..database.enum import UserRole, OrderType, OrderStatus
from ..database.schema import ItalcoUser, Order, OrderServiceUser, ServiceUser


import_bp = Blueprint('import_bp', __name__)


SERVICE_ID = 45
PRODUCT_STRING = 'Ordine importato da file'


@import_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def order_import(user: ItalcoUser):
  if 'file' not in request.files:
    return {'status': 'ko', 'error': 'Nessun file caricato'}

  service_user = get_service_user(request.form['customer_id'])
  for index, row in pd.read_excel(request.files['file']).iterrows():
    create(
      OrderServiceUser,
      {
        'product': PRODUCT_STRING,
        'service_user_id': service_user.id,
        'order_id': create(
          Order,
          {
            'type': OrderType.DELIVERY,
            'status': OrderStatus.PENDING,
            'addressee': row['Destinatario'],
            'address': f'{row["Località"]} {row["Prov."]}',
            'addressee_contact': row['Ref.'],
            'cap': row['CAP'],
            'drc': row['DRC'],
            'dpc': row['DPC'],
            'collection_point_id': request.form['collection_point_id'],
            'customer_note': f'Ref: {row["Rif. Cli."]}, Note: {row["Note + Note Conf. SIEM"]}',
          },
        ).id,
      },
    )

  return {'status': 'ok', 'message': 'Operazione completata'}


def get_service_user(user_id: int) -> ServiceUser:
  with Session() as session:
    return (
      session.query(ServiceUser).filter(ServiceUser.user_id == user_id, ServiceUser.service_id == SERVICE_ID).first()
    )
