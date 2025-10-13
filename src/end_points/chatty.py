import os
import openai
from flask import request, Blueprint

from ..database.schema import ItalcoUser
from api.users import flask_session_authentication
from .orders.queries import query_orders


chatty_bp = Blueprint('chatty_bp', __name__)
openai.api_key = os.getenv('OPEN_AI_KEY')


@flask_session_authentication
@chatty_bp.route('message', methods=['POST'])
def send_message(user: ItalcoUser):
  response = openai.chat.completions.create(
    model='gpt-4o',
    messages=[
      {'role': 'system', 'content': 'Sei Chatty, l\'assistente di Italco.'},
      {'role': 'system', 'content': 'Ecco la lista aggiornata degli ordini dell\'utente:\n\n' +
        ' - '.join([serialize_order(order) for order in query_orders(user, [])]) +
        '\n\nUsa queste informazioni per rispondere alle domande dell\'utente o aggiornarlo sullo stato dei suoi ordini.'},
      {'role': 'user', 'content': request.json['message']}
    ]
  )

  return {
    'status': 'ok',
    'message': response.choices[0].message.content
  }
  

def serialize_order(order_tuple):
  order, order_service_user, service_user, service, italco_user, collection_point = order_tuple
  return (
    f'Ordine ID: {order.id}\n'
    f'Stato: {order.status.name}\n'
    f'Tipo servizio: {service.type.name}\n'
    f'Prodotto: {order_service_user.product}\n'
    f'Prezzo: {service_user.price}€\n'
    f'Indirizzo: {order.address}\n'
    f'CAP: {order.cap}\n'
    f'Data prevista consegna: {order.dpc}\n'
    f'Ritardo: {"Sì" if order.delay else "No"}\n'
    f'Anomalia: {"Sì" if order.anomaly else "No"}\n'
    f'---'
  )
