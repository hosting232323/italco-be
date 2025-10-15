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
@flask_session_authentication([UserRole.ADMIN])
def send_message(user: ItalcoUser):
  today = datetime.now().date()
  two_weeks_ago = today - timedelta(days=14)
  
  orders = []
  for tupla in query_orders(user, [{
    'model': 'Order', 
    'field': 'created_at', 
    'value': [ two_weeks_ago, today ]
    }]):
    orders = format_query_result(tupla, orders, user)
  
  response = openai.chat.completions.create(
    model='gpt-4o',
    messages=[
      {'role': 'system', 'content': 'Sei Chatty, l\'assistente di Italco.'},
      {'role': 'system', 'content': 'Ecco la lista aggiornata degli ordini dell\'utente:\n\n' +
        ' - '.join(str(order) for order in orders) +
        '\n\nUsa queste informazioni per rispondere alle domande dell\'utente o aggiornarlo sullo stato dei suoi ordini.'},
      {'role': 'user', 'content': request.json['message']}
    ]
  )

  return {
    'status': 'ok',
    'message': response.choices[0].message.content
  }
