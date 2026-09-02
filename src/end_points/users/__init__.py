import secrets
import string
from flask import Blueprint, request

from ...database.enum import UserRole
from .session import get_token_payload, refresh_access_token_response, replace_access_token
from .. import auth, flask_session_authentication
from api.users.security import hash_password, verify_password
from ...database.queries import get_user_by_email
from database_api.operations import delete, get_by_id, create, update
from ...database.schema import User, DeliveryUserInfo, CustomerUserInfo
from .queries import (
  query_users,
  format_user_with_info,
  count_user_dependencies,
  get_user_info,
)


user_bp = Blueprint('user_bp', __name__)


def _generate_password(length=12) -> str:
  alphabet = string.ascii_letters + string.digits
  return ''.join(secrets.choice(alphabet) for _ in range(length))


@user_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def cancell_user(user: User, id):
  user: User = get_by_id(User, int(id))
  if not user:
    return {'status': 'ko', 'message': 'Utente non trovato'}

  if request.args.get('force'):
    delete(user)
    return {'status': 'ok', 'message': 'Utente eliminato'}
  else:
    return {'status': 'ko', 'dependencies': count_user_dependencies(int(id))}


@user_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.DELIVERY, UserRole.OPERATOR])
def get_users(user: User):
  return {'status': 'ok', 'users': [format_user_with_info(result, user.role) for result in query_users(user)]}


@user_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_user(_):
  role = UserRole(request.json['role'])
  if not role or role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
    return {'status': 'error', 'message': 'Role not valid'}

  # L'email è unica su tutto il database, non per company: il login avviene
  # prima di sapere quale sia il tenant. get_user_by_email cerca fuori scope
  # apposta, altrimenti un'email già presa altrove sembrerebbe libera.
  if get_user_by_email(request.json['email']):
    return {'status': 'ko', 'message': 'Email già in uso'}

  password = request.json['password']
  create(
    User,
    {
      'role': role,
      'email': request.json['email'],
      'password': hash_password(password),
    },
  )
  return {'status': 'ok', 'message': 'Utente registrato', 'password': password}


@user_bp.route('login', methods=['POST'])
def login():
  password = request.json['password']
  user: User = get_user_by_email(request.json['email'])
  if not user or user.email != request.json['email']:
    return {'status': 'ko', 'message': 'Credenziali errate'}

  def verify(fresh: User, session) -> bool:
    # Verifica sotto lo stesso lock che crea la sessione, così un reset
    # concorrente non può riaprire l'accesso con la password vecchia.
    return check_password(fresh, password)

  extra = {
    'user_id': user.id,
    'role': user.role.value,
    'company': user.company.to_dict() if user.company else None,
  }
  response = auth.login_response(user, extra, verify=verify)
  if response is None:
    return {'status': 'ko', 'message': 'Credenziali errate'}
  return replace_access_token(response, user)


def check_password(user: User, password: str) -> bool:
  return verify_password(password, user.password)


@user_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.ADMIN])
def update_user(_, id):
  user: User = get_by_id(User, int(id))
  if not user:
    return {'status': 'ko', 'message': 'Utente non trovato'}
  if user.role == UserRole.ADMIN:
    return {'status': 'ko', 'message': 'Non è possibile modificare un admin'}

  email = (request.json.get('email') or '').strip()
  password = (request.json.get('password') or '').strip()

  if email and email != user.email and get_user_by_email(email):
    return {'status': 'ko', 'message': 'Email già in uso'}

  with auth.user_session_lock(user.id) as session:
    fresh = session.query(User).filter(User.id == user.id).one()
    data = {}
    if email:
      data['email'] = email
    if password:
      data['password'] = hash_password(password)
      auth.revoke_user_sessions(user.id, db=session)
    if data:
      update(fresh, data, session=session)

  return {'status': 'ok', 'message': 'Utente aggiornato'}


@user_bp.route('<id>/password', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def reset_password(_, id):
  user: User = get_by_id(User, int(id))
  if not user:
    return {'status': 'ko', 'message': 'Utente non trovato'}
  if user.role == UserRole.ADMIN:
    return {'status': 'ko', 'message': 'Non è possibile reimpostare la password di un admin'}

  password = (request.json or {}).get('password') or _generate_password()
  with auth.user_session_lock(user.id) as session:
    fresh = session.query(User).filter(User.id == user.id).one()
    update(fresh, {'password': hash_password(password)}, session=session)
    auth.revoke_user_sessions(user.id, db=session)
  return {'status': 'ok', 'password': password}


@user_bp.route('refresh', methods=['POST'])
def refresh():
  previous_payload = get_token_payload()
  return refresh_access_token_response(auth.refresh(), previous_payload)


@user_bp.route('logout', methods=['POST'])
def logout():
  return auth.logout()


@user_bp.route('position', methods=['POST'])
@flask_session_authentication([UserRole.DELIVERY])
def update_position(user: User):
  save_user_info(user.id, {'lat': float(request.json['lat']), 'lon': float(request.json['lon'])}, DeliveryUserInfo)
  return {'status': 'ok', 'message': 'Posizione aggiornata'}


@user_bp.route('info', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def save_user_info_endpoint(_):
  save_user_info(
    request.json['user_id'],
    request.json['data'],
    DeliveryUserInfo if request.json['class'] == 'Delivery' else CustomerUserInfo,
  )
  return {'status': 'ok', 'message': 'Informazioni utente aggiornate'}


def save_user_info(user_id: int, params: dict, klass):
  user_info = get_user_info(user_id, klass)
  if not user_info:
    create(klass, {**params, 'user_id': user_id})
  else:
    update(user_info, params)
