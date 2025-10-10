import os
import openai
from flask import request

from ..database.schema import ItalcoUser
from api.users import flask_session_authentication
from .orders.queries import query_orders


openai.api_key = os.getenv('OPEN_AI_KEY')


@flask_session_authentication
def send_message_(user: ItalcoUser):
  orders = query_orders(user)
  print(orders)
  return {
    'status': 'ok',
    'message': openai.chat.completions.create(
      model='gpt-4',
      messages=[
        {'role': 'system', 'content': 'Sei Chatty, un assistente virtuale, sei a conoscenza delle mie attivit\u00e0 e delle mie cose da fare e devi aiutarmi a gestire la mia giornata. Chiamami Vanni'},
        {'role': 'system', 'content': '\n'},
        {'role': 'user', 'content': request.json['message']}
      ]
    ).choices[0].message.content
  }

