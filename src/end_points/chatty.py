import os
from flask import request, Blueprint
from datetime import datetime, timedelta

from ..database.schema import User, Chatty
from ..database.enum import UserRole
from .users.session import flask_session_authentication
from .orders.queries import query_orders, format_query_result
from openai import OpenAI
from database_api.operations import create

client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
assistant_id = os.environ['ASSISTANT_ID']
chatty_bp = Blueprint('chatty_bp', __name__)

@chatty_bp.route('message', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.DELIVERY])
def send_message(user: User):
  message = request.json['message']
  if request.json.get('thread_id'):
    thread_id = request.json.get('thread_id')
  else:
    thread_id = client.beta.threads.create().id
    create(Chatty, {
        'thread_id': thread_id
    })

  orders = get_order_for_chatty(user)
  orders_text = (
    "Ecco la lista aggiornata degli ordini nelle ultime due settimane:\n\n"
    + "\n".join(f"- {o}" for o in orders)
    if orders
    else "Non risultano ordini recenti nel sistema."
  )
  
  client.beta.threads.messages.create(
    thread_id=thread_id,
    role="user",
    content=f"Domanda: {message}\n{orders_text}"
  )
  
  run = client.beta.threads.runs.create(
    thread_id=thread_id,
    assistant_id=assistant_id
  )

  while True:
    run_status = client.beta.threads.runs.retrieve(
      thread_id=thread_id,
      run_id=run.id
    )

    if run_status.status == 'completed':
      break

  messages = client.beta.threads.messages.list(thread_id=thread_id)
  response = messages.data[0].content[0].text.value
  return {"message": response, "thread_id": thread_id, "status": "ok"}


@chatty_bp.route('thread/<thread_id>', methods=['GET'])
def get_thread_messages(thread_id):
  messages_response = client.beta.threads.messages.list(thread_id=thread_id)
  messages = []
  for m in messages_response.data:
    for c in m.content:
      if hasattr(c, 'text') and hasattr(c.text, 'value'):
        messages.append({
          'role': m.role,
          'text': c.text.value
        })
  return {'status': 'ok', 'thread_id': thread_id, 'messages': messages}



def get_order_for_chatty(user: User) -> list[dict]:
  today = datetime.now().date()
  two_weeks_ago = today - timedelta(days=7)
  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'created_at', 'value': [two_weeks_ago, today]}]):
    orders = format_query_result(tupla, orders, user)
  return orders
