import os
import json

from api.users.security import hash_password
from flask import Blueprint, request, send_from_directory

from sqlalchemy import desc

from . import flask_session_authentication
from .. import STATIC_FOLDER
from ..database.enum import UserRole
from ..database.schema import Company, User
from ..database.queries import get_user_by_nickname
from .rae.disposal_place import (
  count_rae_disposal_places,
  create_rae_disposal_place,
  delete_rae_disposal_place,
  get_rae_disposal_places,
  update_rae_disposal_place,
)
from .users.session import create_jwt_token
from database_api import Session, scope
from database_api.operations import create, get_by_id, update
from api.storage import get_full_path
from api.storage.files import validate_files, IMAGE_EXTENSIONS
from api.storage.utils import guess_extension, get_base_file_path
from api.storage.session import SessionWithStorage


company_bp = Blueprint('company_bp', __name__)


# Cartella dei loghi aziendali, sotto STATIC_FOLDER come le foto degli ordini.
LOGO_SUBFOLDER = 'company-logos'

# Dati legali dell'attività stampati nei PDF (oggi il DDT RAEE). A DB sono tutti
# nullable: qui vive il vincolo, come già per 'name'. Sempre obbligatori, col
# modulo RAEE acceso o no: i dati specifici RAEE (iscrizione Albo, luogo di
# raggruppamento) non sono più qui, vivono su RaeDisposalPlace perché una
# company può averne N. tax_code e logo restano opzionali.
ALWAYS_REQUIRED_LEGAL = ('legal_name', 'vat_number', 'address', 'city')
LEGAL_FIELDS = ALWAYS_REQUIRED_LEGAL + ('tax_code',)

LEGAL_LABELS = {
  'legal_name': 'Ragione sociale',
  'vat_number': 'Partita IVA',
  'address': 'Indirizzo sede legale',
  'city': 'Città',
}

RAE_WITHOUT_PLACE_ERROR = 'Configura almeno un luogo di smaltimento RAEE prima di attivare il modulo'


def _payload() -> dict:
  """Body della richiesta, dal campo 'data' del FormData quando c'è il logo,
  altrimenti dal JSON."""
  data = request.form.get('data')
  if isinstance(data, str):
    return json.loads(data)
  return request.get_json(silent=True) or {}


def _clean_legal(payload: dict, *, only_present: bool) -> dict:
  fields = [field for field in LEGAL_FIELDS if field in payload] if only_present else LEGAL_FIELDS
  return {field: ((payload.get(field) or '').strip() or None) for field in fields}


def _legal_error(legal: dict) -> str | None:
  missing = [
    LEGAL_LABELS[field]
    for field in ALWAYS_REQUIRED_LEGAL
    # In creazione i campi ci sono tutti; in modifica si valida solo ciò che
    # arriva, così un rename non deve rispedire l'anagrafica intera.
    if field in legal and not legal[field]
  ]
  if missing:
    return f'Campi obbligatori mancanti: {", ".join(missing)}'
  return None


def _store_logo(company_id: int, uploaded_file, session: SessionWithStorage) -> str:
  filename = f'{company_id}{guess_extension(uploaded_file.mimetype)}'
  stored_path = session.upload(uploaded_file, filename, STATIC_FOLDER, subfolder=LOGO_SUBFOLDER)
  return get_base_file_path('company/logo') + os.path.basename(stored_path)


# tenant_required=False: sono gli unici endpoint raggiungibili da un super admin
# che non ha ancora scelto una company.
@company_bp.route('', methods=['GET'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def get_companies(_):
  return {'status': 'ok', 'companies': [company.to_dict() for company in query_companies()]}


def query_companies() -> list[Company]:
  with Session() as session:
    return session.query(Company).order_by(desc(Company.created_at)).all()


@company_bp.route('', methods=['POST'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def create_company(_):
  error = validate_files(request.files.values(), IMAGE_EXTENSIONS)
  if error:
    return {'status': 'ko', 'message': error}

  payload = _payload()
  name = (payload.get('name') or '').strip()
  if not name:
    return {'status': 'ko', 'message': 'Nome obbligatorio'}

  admin_nickname = (payload.get('admin_nickname') or '').strip()
  admin_password = (payload.get('admin_password') or '').strip()
  if not admin_nickname:
    return {'status': 'ko', 'message': 'Nickname admin obbligatorio'}
  if not admin_password:
    return {'status': 'ko', 'message': 'Password admin obbligatoria'}

  if get_user_by_nickname(admin_nickname):
    return {'status': 'ko', 'message': 'Nickname già in uso'}

  # bool() esplicito: dal client il flag può arrivare assente, ed è il caso
  # normale di un'attività appena creata. Il modulo RAEE nasce spento, e così
  # la pianificazione automatica degli ordini.
  rae = bool(payload.get('rae'))
  automatic_planning = bool(payload.get('automatic_planning'))
  legal = _clean_legal(payload, only_present=False)
  legal_error = _legal_error(legal)
  if legal_error:
    return {'status': 'ko', 'message': legal_error}
  # Una company appena creata non può ancora avere un luogo di smaltimento
  # (ci vuole il suo id): con rae=true in creazione il modulo si accenderebbe
  # senza che nessun luogo esista.
  if rae:
    return {'status': 'ko', 'message': RAE_WITHOUT_PLACE_ERROR}

  company = create(Company, {'name': name, 'rae': rae, 'automatic_planning': automatic_planning, **legal})

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

  logo_file = request.files.get('logo')
  if logo_file:
    with SessionWithStorage() as session:
      link = _store_logo(company.id, logo_file, session)
      update(get_by_id(Company, company.id, session=session), {'logo': link}, session=session)
      session.commit()
    company = get_by_id(Company, company.id)

  return {'status': 'ok', 'company': company.to_dict()}


@company_bp.route('<id>', methods=['PUT'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def update_company(_, id):
  error = validate_files(request.files.values(), IMAGE_EXTENSIONS)
  if error:
    return {'status': 'ko', 'message': error}

  payload = _payload()
  name = (payload.get('name') or '').strip()
  if not name:
    return {'status': 'ko', 'message': 'Nome obbligatorio'}
  if 'rae' in payload and not isinstance(payload['rae'], bool):
    return {'status': 'ko', 'message': 'Il flag RAEE deve essere booleano'}
  if 'automatic_planning' in payload and not isinstance(payload['automatic_planning'], bool):
    return {'status': 'ko', 'message': 'Il flag di pianificazione automatica deve essere booleano'}

  logo_file = request.files.get('logo')

  # Update and serialize the company in the same transaction, so both the
  # response and the next list read reflect the persisted database row.
  with SessionWithStorage() as session:
    company: Company = get_by_id(Company, int(id), session=session)
    if not company:
      return {'status': 'ko', 'message': 'Company non trovata'}

    rae = payload['rae'] if 'rae' in payload else company.rae
    legal = _clean_legal(payload, only_present=True)
    legal_error = _legal_error(legal)
    if legal_error:
      return {'status': 'ko', 'message': legal_error}
    if rae and count_rae_disposal_places(int(id)) == 0:
      return {'status': 'ko', 'message': RAE_WITHOUT_PLACE_ERROR}

    changes = {'name': name, **legal}
    if 'rae' in payload:
      changes['rae'] = payload['rae']
    if 'automatic_planning' in payload:
      changes['automatic_planning'] = payload['automatic_planning']
    if logo_file:
      changes['logo'] = _store_logo(int(id), logo_file, session)

    update(company, changes, session=session)
    session.commit()
    response_company = get_by_id(Company, int(id), session=session).to_dict()

  return {'status': 'ok', 'company': response_company}


@company_bp.route('logo/<filename>', methods=['GET'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False, allow_query_token=True)
def serve_company_logo(_, filename):
  return send_from_directory(get_full_path(STATIC_FOLDER, LOGO_SUBFOLDER), filename)


@company_bp.route('<company_id>/rae-disposal-place', methods=['GET'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def get_company_rae_disposal_places(_, company_id):
  return get_rae_disposal_places(int(company_id))


@company_bp.route('<company_id>/rae-disposal-place', methods=['POST'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def create_company_rae_disposal_place(_, company_id):
  return create_rae_disposal_place(int(company_id), request.json)


@company_bp.route('<company_id>/rae-disposal-place/<id>', methods=['PUT'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def update_company_rae_disposal_place(_, company_id, id):
  return update_rae_disposal_place(int(company_id), int(id), request.json)


@company_bp.route('<company_id>/rae-disposal-place/<id>', methods=['DELETE'])
@flask_session_authentication([UserRole.SUPER_ADMIN], tenant_required=False)
def delete_company_rae_disposal_place(_, company_id, id):
  return delete_rae_disposal_place(int(company_id), int(id))


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
