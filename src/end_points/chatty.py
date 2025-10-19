import os
import openai
from flask import request, Blueprint
from datetime import datetime, timedelta

from ..database.enum import UserRole
from .orders.queries import query_orders, format_query_result
from ..database.schema import ItalcoUser
from . import flask_session_authentication


openai.api_key = os.getenv('OPEN_AI_KEY')
chatty_bp = Blueprint('chatty_bp', __name__)


@chatty_bp.route('message', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.DELIVERY])
def send_message(user: ItalcoUser):
  response = openai.chat.completions.create(
    model='gpt-4o',
    messages=[
      {
        'role': 'system',
        'content': "Sei Chatty, l'assistente di Italcomi, un'azienda che si occupa di consegne di elettrodomestici."
        + "Evita qualsiasi domanda che non abbia a che fare con l'azienda e i suoi ordini",
      },
      {
        'role': 'system',
        'content': "Ecco la lista aggiornata degli ordini dell'utente:\n\n"
        + ' - '.join(str(order) for order in get_order_for_chatty(user))
        + "\n\nUsa queste informazioni per rispondere alle domande dell'utente o aggiornarlo sullo stato dei suoi ordini.",
      },
      {'role': 'user', 'content': request.json['message']},
    ],
  )

  return {'status': 'ok', 'message': response.choices[0].message.content}


def get_order_for_chatty(user: ItalcoUser) -> list[dict]:
  today = datetime.now().date()
  two_weeks_ago = today - timedelta(days=7)
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'created_at', 'value': [two_weeks_ago, today]}]):
    orders = format_query_result(tupla, orders, user)
  return orders
