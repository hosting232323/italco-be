import pandas as pd
from flask import Blueprint, request
from geopy.geocoders import Nominatim

from database_api import Session
from database_api.operations import create
from ..database.enum import UserRole, OrderType
from . import error_catching_decorator, flask_session_authentication
from ..database.schema import ItalcoUser, Order, Addressee, OrderServiceUser


import_bp = Blueprint('import_bp', __name__)

# Euronics martinafranca
# Euronics Monopoli	Eur026432 CL 9
# consegna al piano con installazione (allaccio alla prese)


USER_ID = 0
COLLECTION_POINT_ID = 0
SERVICE_USER_ID = 0


@import_bp.route('', methods=['POST'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def update_import(user: ItalcoUser):
  if 'file' not in request.files:
    return {
      'status': 'ko',
      'error': 'Nessun file caricato'
    }

  df = pd.read_excel(request.files['file'])
  for index, row in df.iterrows():
    addressee = query_addressee(row['Destinatario'], row['Indirizzo'])
    if addressee is None:
      addressee = create(Addressee, {
        'name': row['Destinatario'],
        'address': row['Indirizzo'],
        'city': row['Località'],
        'cap': get_cap_from_city(row['Località']),
        'province': row['Prov.'],
        'user_id': USER_ID
      })
    order = create(Order, {
      'type': OrderType.DELIVERY,
      'collection_point_id': COLLECTION_POINT_ID,
      'addressee_id': addressee.id,
      'drc': row['DRC'],
      'dpc': row['DPC'],
      'customer_note': f'Ref: {row["Ref."]} ' \
        f'Preavviso: {row["Preavviso"]} ' \
        f'Fascia: {row["Fascia"]} ' \
        f'Note: {row["Note + Note Conf. SIEM"]}'
    })
    create(OrderServiceUser, {
      'order_id': order.id,
      'service_user_id': SERVICE_USER_ID
    })

  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }


def query_addressee(name, address) -> Addressee:
  with Session() as session:
    return session.query(Addressee).filter(
      Addressee.name == name,
      Addressee.address == address
    ).first()


def get_cap_from_city(city_name: str) -> str:
  location = Nominatim(user_agent='cap_lookup_app').geocode(f'{city_name}, Italy', addressdetails=True)
  if location and 'postcode' in location.raw['address']:
    return location.raw['address']['postcode']
  else:
    return 'CAP non trovato'
