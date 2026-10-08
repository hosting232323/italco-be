import os
import re
import time
import threading
from flask import request, Blueprint

from api.email import send_email
from database_api.operations import create
from .orders.mailer import MAILS
from ..database.schema import Mail


demo_request_bp = Blueprint('demo_request_bp', __name__)

# Destinatari delle richieste. Il destinatario non arriva mai dal client (a
# differenza di /send-mail di generic-be): l'endpoint e' pubblico e altrimenti
# sarebbe un relay aperto. Senza variabile valgono gli indirizzi operativi
# gia' usati per le email degli ordini.
DEMO_REQUEST_EMAILS = [
  email.strip() for email in os.environ.get('DEMO_REQUEST_EMAILS', '').split(',') if email.strip()
] or MAILS

RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 3600

EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# (chiave, etichetta nell'email, lunghezza massima, obbligatorio)
FIELDS = [
  ('nome', 'Nome', 100, True),
  ('azienda', 'Ragione sociale', 150, True),
  ('email', 'Email aziendale', 150, True),
  ('cellulare', 'Cellulare', 30, True),
  ('partita_iva', 'Partita IVA', 30, False),
  ('attivita', 'Attività', 100, False),
  ('indirizzo', 'Indirizzo', 200, False),
  ('citta', 'Città', 100, False),
  ('cap', 'CAP', 12, False),
  ('messaggio', 'Messaggio', 2000, False),
]

_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()


def client_ip() -> str:
  # Dietro il proxy remote_addr e' quello del proxy: conta il primo hop di
  # X-Forwarded-For. Il limite e' un freno agli abusi, non una barriera.
  forwarded = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
  return forwarded or request.remote_addr or 'unknown'


def rate_limited(ip: str) -> bool:
  now = time.time()
  with _attempts_lock:
    recent = [stamp for stamp in _attempts.get(ip, []) if now - stamp < RATE_LIMIT_WINDOW_SECONDS]
    if len(recent) >= RATE_LIMIT_MAX:
      _attempts[ip] = recent
      return True
    recent.append(now)
    _attempts[ip] = recent
    # Sfoltisce le voci scadute degli altri indirizzi, cosi' il dizionario non cresce all'infinito.
    for other in [
      key for key, stamps in _attempts.items() if not any(now - s < RATE_LIMIT_WINDOW_SECONDS for s in stamps)
    ]:
      del _attempts[other]
    return False


def clean(value, max_length: int, multiline: bool = False) -> str | None:
  if value is None:
    return ''
  if not isinstance(value, str):
    return None
  value = CONTROL_CHARS.sub('', value)
  # Solo il messaggio puo' andare a capo: gli altri campi finiscono anche
  # nell'oggetto dell'email, dove un a-capo aprirebbe un nuovo header.
  value = value.strip() if multiline else ' '.join(value.split())
  return value if len(value) <= max_length else None


def parse_request(data) -> tuple[dict | None, str | None]:
  if not isinstance(data, dict):
    return None, 'Richiesta non valida'
  values = {}
  for key, label, max_length, required in FIELDS:
    value = clean(data.get(key), max_length, multiline=key == 'messaggio')
    if value is None:
      return None, f'{label} non valido'
    if required and not value:
      return None, f'{label} obbligatorio'
    values[key] = value
  if not EMAIL_REGEX.match(values['email']):
    return None, 'Email aziendale non valida'
  if len(re.sub(r'\D', '', values['cellulare'])) < 6:
    return None, 'Numero di cellulare non valido'
  return values, None


def build_content(values: dict) -> dict:
  lines = []
  for key, label, _, _ in FIELDS:
    if key != 'messaggio':
      lines.append(f'{label}: {values[key] or "Non indicato"}')
  message = values['messaggio'] or 'Vorrei conoscere HUBSTRA e le sue funzionalità.'
  return {
    'subject': f'Richiesta demo HUBSTRA — {values["azienda"]}',
    'text': '\n'.join(lines) + f'\n\nMessaggio:\n{message}',
  }


@demo_request_bp.route('', methods=['POST'])
def demo_request_endpoint():
  # Campo trappola, invisibile nella pagina: lo riempiono solo i bot. Si
  # risponde ok senza fare nulla, cosi' non sanno di essere stati scartati.
  data = request.get_json(silent=True)
  if isinstance(data, dict) and data.get('sito_web'):
    return {'status': 'ok', 'message': 'Richiesta inviata'}

  values, error = parse_request(data)
  if error:
    return {'status': 'ko', 'message': error}, 400
  if rate_limited(client_ip()):
    return {'status': 'ko', 'message': 'Troppe richieste, riprova più tardi'}, 429

  content = build_content(values)
  # Salvata prima dell'invio: se l'SMTP e' giu' il contatto resta comunque in archivio.
  for recipient in DEMO_REQUEST_EMAILS:
    create(
      Mail,
      {
        'origin': request.headers.get('Origin'),
        'recipient': recipient,
        'subject': content['subject'],
        'content': content['text'],
      },
    )

  delivered = [send_email(recipient, content['text'], content['subject']) for recipient in DEMO_REQUEST_EMAILS]
  # Basta un destinatario raggiunto: la richiesta e' arrivata a qualcuno.
  if not any(delivered):
    return {'status': 'ko', 'message': 'Invio non riuscito, riprova più tardi o contattaci direttamente'}, 502
  return {'status': 'ok', 'message': 'Richiesta inviata'}
