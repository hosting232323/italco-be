import os
from flask import request, Blueprint
from datetime import datetime, timedelta

from ..database.schema import User, Chatty
from ..database.enum import UserRole
from .users.session import flask_session_authentication
from .orders.queries import query_orders, format_query_result
from . import flask_session_authentication
from openai import OpenAI
from database_api.operations import create

client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
chatty_bp = Blueprint('chatty_bp', __name__)


@chatty_bp.route('message', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.DELIVERY])
def send_message(user: User):
  message = request.json['message']
  if request.json['thread_id']:
    thread_id = request.json['thread_id']
  else:
    thread_id = client.beta.threads.create().id
    create(Chatty, {
      thread_id: thread_id
    })

  orders = get_order_for_chatty(user)
  orders_text = (
    "Ecco la lista aggiornata dei tuoi ordini nelle ultime due settimane:\n\n"
    + "\n".join(f"- {o}" for o in orders)
    if orders
    else "Non risultano ordini recenti nel sistema."
  )
  
  client.beta.threads.messages.create(
    thread_id=thread_id,
    role="user",
    content=f"{user_message}\n\n{orders_text}",
  )

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


def get_order_for_chatty(user: User) -> list[dict]:
  today = datetime.now().date()
  two_weeks_ago = today - timedelta(days=7)
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'created_at', 'value': [two_weeks_ago, today]}]):
    orders = format_query_result(tupla, orders, user)
  return orders
