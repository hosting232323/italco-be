import os
import json
from openai import OpenAI
from flask import request, Blueprint
from datetime import datetime, timedelta
import re

from ..database.enum import UserRole
from ..database.schema import User, Chatty
from database_api.operations import create
from .users.session import flask_session_authentication
from .orders.queries import query_orders, format_query_result
from flask import Response, stream_with_context, request

MAX_TOOL_OUTPUT_BYTES = 450_000
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
assistant_id = os.environ['ASSISTANT_ID']
chatty_bp = Blueprint('chatty_bp', __name__)

@chatty_bp.route('message/stream', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN, UserRole.OPERATOR, UserRole.CUSTOMER, UserRole.DELIVERY])
def send_stream(user: User):

  body = request.get_json()

  if body.get("thread_id"):
    thread_id = body["thread_id"]
  else:
    thread_id = client.beta.threads.create().id
    create(Chatty, {'thread_id': thread_id})

  client.beta.threads.messages.create(
    thread_id=thread_id,
    role="user",
    content=body["message"]
  )

  def generate():
    run_id = None

    with client.beta.threads.runs.stream(
      thread_id=thread_id,
      assistant_id=assistant_id
    ) as stream:
      run_id = None
      for event in stream:
        if event.event == "thread.run.created":
          run_id = event.data.id

        elif event.event == "thread.run.requires_action":

          for tool_call in event.data.required_action.submit_tool_outputs.tool_calls:

            if tool_call.function.name == "get_order_for_chatty":

              tool_inputs = json.loads(tool_call.function.arguments)
              start_date = tool_inputs.get("start_date")
              end_date = tool_inputs.get("end_date")

              orders = get_order_for_chatty(user, start_date, end_date)
              date_message = f"dal {start_date}{f' al {end_date}' if end_date else ''}"

              if not orders:
                output_text = f"{date_message}\nNon sono stati trovati ordini."
              else:
                output_text = f"{date_message}\nEcco la lista degli ordini:\n"
                output_bytes = len(output_text.encode("utf-8"))

                for o in orders:
                  order_str = json.dumps(o, ensure_ascii=False) + "\n"
                  order_bytes = len(order_str.encode("utf-8"))
                  if output_bytes + order_bytes > MAX_TOOL_OUTPUT_BYTES:
                    output_text += "Elenco di ordini troncato"
                    break
                  output_text += order_str
                  output_bytes += order_bytes

              print(output_text)
              client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread_id,
                run_id=run_id,
                tool_outputs=[
                  {
                    "tool_call_id": tool_call.id,
                    "output": output_text
                  }
                ]
              )

        elif event.event == "thread.message.delta":
          for block in event.data.delta.content:
            if block.type == "text":
              yield block.text.value

  response = Response(
    stream_with_context(generate()),
    mimetype="text/plain"
  )
  response.headers['thread_id'] = thread_id
  return response


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
          submit_orders_to_thread_dynamic(thread_id, run.id, tool_call.id, orders, date_message)

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
  start_dt = datetime.strptime(start_date, '%Y-%m-%d')
  for tupla in query_orders(
    user,
    [
      {
        'model': 'Order',
        'field': 'created_at',
        'value': [start_dt, (datetime.strptime(end_date, '%Y-%m-%d') if end_date else start_dt) + timedelta(days=1)],
      }
    ],
  ):
    orders = format_query_result(tupla, orders, user)
  return orders


def submit_orders_to_thread_dynamic(
  thread_id: str, run_id: str, tool_call_id: str, orders: list[dict], date_message: str
):
  if not orders:
    output_text = f'{date_message}\nNon sono stati trovati ordini.'
  else:
    output_text = f'{date_message}\nEcco la lista degli ordini:\n'
    output_bytes = len(output_text.encode('utf-8'))

    for o in orders:
      order_str = json.dumps(o, ensure_ascii=False) + '\n'
      order_bytes = len(order_str.encode('utf-8'))
      if output_bytes + order_bytes > MAX_TOOL_OUTPUT_BYTES:
        output_text += 'Elenco di ordini troncato'
        break

      output_text += order_str
      output_bytes += order_bytes

  client.beta.threads.runs.submit_tool_outputs(
    thread_id=thread_id, run_id=run_id, tool_outputs=[{'tool_call_id': tool_call_id, 'output': output_text}]
  )
