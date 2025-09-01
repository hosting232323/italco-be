from flask import Blueprint, request

from database_api import Session
from ...database.enum import UserRole
from api import error_catching_decorator
from api.users import register_user, login
from database_api.operations import delete
from .. import flask_session_authentication
from api.users.setup import get_user_by_email
from ...database.schema import ItalcoUser, ServiceUser, CollectionPoint

user_bp = Blueprint('user_bp', __name__)


@user_bp.route('<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.ADMIN])
def cancell_user(user: ItalcoUser, id):
  result_query = deletion_query(int(id))
  if not result_query:
    return {'status': 'ko', 'error': 'Utente non trovato'}

  entity_related = []
  if not request.args.get('force'):
    if any(result[1] for result in result_query):
      entity_related.append('Relazioni con Servizi')
    if any(result[2] for result in result_query):
      entity_related.append('Anagrafiche')
    if any(result[3] for result in result_query):
      entity_related.append('Punti di ritiro')

  if request.args.get('force') or len(entity_related) == 0:
    delete(result_query[0][0])
    return {'status': 'ok', 'message': 'Utente eliminato'}
  else:
    return {
      'status': 'ko',
      'error': 'Sei sicuro di voler eliminare questo utente? '
      f'Saranmno cancellati i seguenti dati correlati: {", ".join(entity_related)}',
    }


@user_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.ADMIN, UserRole.DELIVERY, UserRole.OPERATOR])
def get_users(user: ItalcoUser):
  return {'status': 'ok', 'users': [result.format_user(user.role) for result in query_users(user)]}


@user_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.ADMIN])
def create_user(user: ItalcoUser):
  role = UserRole.get_enum_option(request.json['role'])
  if not role or role == UserRole.ADMIN:
    return {'status': 'error', 'message': 'Role not valid'}

  return register_user(request.json['email'], None, request.json['password'], params={'role': role})


@error_catching_decorator
def login_():
  response = login(request.json['email'], request.json['password'])
  if response['status'] == 'ok':
    user: ItalcoUser = get_user_by_email(request.json['email'])
    response['user_info'] = {'id': user.id, 'role': user.role.value}
  return response


def query_users(user: ItalcoUser, role: UserRole = None) -> list[ItalcoUser]:
  with Session() as session:
    query = session.query(ItalcoUser)
    if user.role in [UserRole.DELIVERY, UserRole.OPERATOR]:
      query = query.filter(ItalcoUser.role == UserRole.CUSTOMER)
    if role:
      query = query.filter(ItalcoUser.role == role)
    return query.all()


def deletion_query(id: int) -> list[tuple[ItalcoUser, ServiceUser, CollectionPoint]]:
  with Session() as session:
    return (
      session.query(ItalcoUser, ServiceUser, CollectionPoint)
      .outerjoin(ServiceUser, ServiceUser.user_id == ItalcoUser.id)
      .outerjoin(CollectionPoint, CollectionPoint.user_id == ItalcoUser.id)
      .filter(ItalcoUser.id == id)
      .all()
    )
