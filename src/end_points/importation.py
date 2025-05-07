import pandas as pd
from flask import Blueprint, request

from ..database.enum import UserRole
from ..database.schema import ItalcoUser
from . import error_catching_decorator, flask_session_authentication


import_bp = Blueprint('import_bp', __name__)


@import_bp.route('<id>', methods=['PUT'])
@error_catching_decorator
@flask_session_authentication([UserRole.ADMIN])
def update_import(user: ItalcoUser):
  if 'file' not in request.files:
    return {
      'status': 'ko',
      'error': 'Nessun file caricato'
    }

  df = pd.read_excel(request.files['file'])
  print(df.head())

  return {
    'status': 'ok',
    'message': 'Operazione completata'
  }
