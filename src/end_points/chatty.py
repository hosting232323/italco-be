import os
import json
from openai import OpenAI
from datetime import datetime
from flask import request, Blueprint

from ..database.enum import UserRole
from ..database.schema import User, Chatty
from database_api.operations import create
from .users.session import flask_session_authentication
from .orders.queries import query_orders, format_query_result


client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
assistant_id = os.environ['ASSISTANT_ID']
chatty_bp = Blueprint('chatty_bp', __name__)


@chatty_bp.route('message', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.DELIVERY])
def send_message(user: User):
  if 'thread_id' in request.json and request.json['thread_id']:
    thread_id = request.json['thread_id']
  else:
    thread_id = client.beta.threads.create().id
    create(Chatty, {'thread_id': thread_id})

  user_message = f'Oggi è: {datetime.now().date()}\n\n{request.json["message"]}'
  client.beta.threads.messages.create(thread_id=thread_id, role='user', content=user_message)
  run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id)
  while True:
    run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

    if run_status.status == 'requires_action':
      for tool_call in run_status.required_action.submit_tool_outputs.tool_calls:
        if tool_call.function.name == 'get_order_for_chatty':
          tool_inputs = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
          start_date = tool_inputs.get('start_date')
          end_date = tool_inputs.get('end_date')
          orders = get_order_for_chatty(user, start_date, end_date)
          date_message = f'dal {start_date}{f" al {end_date}" if end_date else ""}'
          client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread_id,
            run_id=run.id,
            tool_outputs=[
              {
                'tool_call_id': tool_call.id,
                'output': (
                  f'Ecco la lista aggiornata degli ordini:\n\n{date_message}' + '\n'.join(str(orders))
                  if orders
                  else 'Non ordine trovato'
                ),
              }
            ],
          )

    elif run_status.status == 'completed':
      break

  return {
    'status': 'ok',
    'thread_id': thread_id,
    'message': client.beta.threads.messages.list(thread_id=thread_id).data[0].content[0].text.value,
  }


@chatty_bp.route('thread/<thread_id>', methods=['GET'])
def get_thread_messages(thread_id):
  messages = []
  for m in client.beta.threads.messages.list(thread_id=thread_id).data:
    for c in m.content:
      if hasattr(c, 'text') and hasattr(c.text, 'value'):
        messages.append({'role': m.role, 'text': c.text.value})
  return {'status': 'ok', 'thread_id': thread_id, 'messages': messages}


def get_order_for_chatty(user: User, start_date: str = None, end_date: str = None) -> list[dict]:
  orders = []
  start = datetime.strptime(start_date, '%Y-%m-%d').date()
  end = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else start
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'created_at', 'value': [start, end]}]):
    orders = format_query_result(tupla, orders, user)
  return orders
