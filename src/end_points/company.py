from api.users.security import hash_password
from flask import Blueprint, request

from . import flask_session_authentication
from ..database.enum import UserRole
from ..database.schema import Company, User
from ..database.queries import get_user_by_nickname
from .users.session import create_jwt_token
from database_api import Session, scope
from database_api.operations import create, get_all, get_by_id


company_bp = Blueprint('company_bp', __name__)


# tenant_required=False: sono gli unici endpoint raggiungibili da un super admin
# che non ha ancora scelto una company.
@company_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def get_companies(_):
  return {'status': 'ok', 'companies': [company.to_dict() for company in get_all(Company)]}


@company_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def create_company(_):
  name = (request.json.get('name') or '').strip()
  if not name:
    return {'status': 'ko', 'message': 'Nome obbligatorio'}

  admin_nickname = (request.json.get('admin_nickname') or '').strip()
  admin_password = (request.json.get('admin_password') or '').strip()
  if not admin_nickname:
    return {'status': 'ko', 'message': 'Nickname admin obbligatorio'}
  if not admin_password:
    return {'status': 'ko', 'message': 'Password admin obbligatoria'}

  if get_user_by_nickname(admin_nickname):
    return {'status': 'ko', 'message': 'Nickname già in uso'}

  # bool() esplicito: dal client il flag può arrivare assente, ed è il caso
  # normale di un'attività appena creata. Il modulo RAEE nasce spento.
  company = create(Company, {'name': name, 'rae': bool(request.json.get('rae'))})

  # Crea l'admin nella company appena nata usando lo scope tenant
  # così il listener set_company_on_insert timbra automaticamente la company_id.
  with scope(company_id=company.id):
    create(
      User,
      {
        'role': UserRole.ADMIN,
        'nickname': admin_nickname,
        'password': hash_password(admin_password),
      },
    )

  return {'status': 'ok', 'company': company.to_dict()}


@company_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def update_company(_, id):
  payload = request.get_json(silent=True) or {}
  name = (payload.get('name') or '').strip()
  if not name:
    return {'status': 'ko', 'message': 'Nome obbligatorio'}
  if 'rae' in payload and not isinstance(payload['rae'], bool):
    return {'status': 'ko', 'message': 'Il flag RAEE deve essere booleano'}

  # Update and serialize the company in the same transaction, so both the
  # response and the next list read reflect the persisted database row.
  with Session() as session, session.begin():
    company: Company = session.get(Company, int(id))
    if not company:
      return {'status': 'ko', 'message': 'Company non trovata'}

    company.name = name
    if 'rae' in payload:
      company.rae = payload['rae']

    session.flush()
    session.refresh(company)
    response_company = company.to_dict()

  return {'status': 'ok', 'company': response_company}


@company_bp.route('select', methods=['POST'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def select_company(user: User):
  """Cambia la company attiva riemettendo il token.

  Lo scope sta nella sessione, non in un header: così ogni richiesta è
  autodescrittiva e nessun endpoint deve validare di volta in volta che quel
  super admin possa vedere quella company. Il campo si chiama new_token perché
  il client http lo raccoglie da solo, senza logica dedicata.
  """
  company_id = request.json.get('company_id')
  company: Company = get_by_id(Company, int(company_id)) if company_id else None
  if company_id and not company:
    return {'status': 'ko', 'message': 'Company non trovata'}

  return {
    'status': 'ok',
    'company': company.to_dict() if company else None,
    'new_token': create_jwt_token(user, company.id if company else None),
  }
