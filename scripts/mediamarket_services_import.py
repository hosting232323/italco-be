# ruff: noqa: E402, T201, E501
"""Importa il listino MediaMarket per l'attività 2 e lo applica ai suoi punti vendita.

I nomi dei servizi sono trascritti alla lettera da "LISTINO MEDIAMARKET.xlsx"
(colonne Codici / DESCRIZIONE SERVIZIO / IC), virgolette tipografiche comprese:
sono la chiave con cui lo script riconosce un servizio già importato, quindi non
vanno "ripuliti" senza rifare l'import. Per lo stesso motivo il blocco LISTINO
supera i 120 caratteri e il file disattiva E501.

Lo script è idempotente: rieseguito, riusa i servizi già presenti nella company
e allinea codice e prezzo dei service_user esistenti invece di duplicarli. Senza
--apply non scrive nulla.
"""

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from database_api import Session, scope, set_database
from database_api.operations import create

from src.database.enum import OrderType, UserRole
from src.database.schema import Company, Service, ServiceUser, User


COMPANY_ID = 2
USER_IDS = [71, 72, 73, 74, 75]

# Il listino ha una colonna sola di importo (IC) e service_user ha un solo campo
# di valore (price): prezzo e costo sono lo stesso numero, non due colonne.
# (codice, nome servizio, importo)
# fmt: off
LISTINO = [
  ('109532', 'STAND TV* – INSTALLAZIONE STAND (consegna e installazione)< 55”', 27),
  ('109534', 'WALL TV* – INSTALLAZIONE WALL TV (consegna e installazione)<55”', 35),
  ('109560', 'SUPPLEMENTO SOUNDBAR x codici ***', 10),
  ('109561', 'SUPPLEMENTO TV GRANDI DIMENSIONI TV ≥ 55’’ e TV ≤ 80” x codici ***', 15),
  ('109562', 'SUPPLEMENTO EXPRESS TV x codici ***', 15),
  ('123619', 'MONTAGGIO KIT COLONNA BUCATO', 10),
  ('123620', 'CONSEGNA COMFORT PLUS FASCIA 1* (consegna 9-13/14-18 il giorno seguente all’acquisto) inclusiva di allacciamento', 27),
  ('126930', 'SUPPLEMENTO COMFORT PLUS x codici ** (Escluso cod.123620)', 2),
  ('156452', 'ALLACCIAMENTO FILTRO ANTI CALCARE', 1.5),
  ('177583', 'CONSEGNA COMFORT (24) FASCIA 1* (consegna 9-13/14-18 il giorno seguente all’acquisto) inclusiva di allacciamento', 27),
  ('204308', 'CONSEGNA COMFORT (48) FASCIA 1* (consegna 9-13/14-18 il giorno seguente all’acquisto) inclusiva di allacciamento', 27),
  ('323299', 'DISINCASSO senza nuovo incasso (e ritiro)', 15),
  ('405322', 'SUPPLEMENTO TV GRANDI DIMENSIONI TV > 80’’ x codici *** Vedi dettaglio capitolato', 35),
  ('550450', 'CONSEGNA EXPRESS FASCIA 1* (consegna 18-21 lo stesso giorno dell’acquisto) inclusiva di allacciamento', 40),
  ('612785', 'SOSTITUZIONE UGELLI (solo servizio di sostituzione ugelli senza alcuna installazione)', 20),
  ('612825', 'INCASSO PIANO COTTURA/FORNO A GAS E CERTIFICAZIONE (senza consegna)', 35),
  ('612887', 'INCASSO PIANO COTTURA/FORNO/CUCINE A GAS CON CONSEGNA E CERTIFICAZIONE', 40),
  ('612921', 'SMONTAGGIO COLONNE FRIGO INCASSO (con consegna nuovo prodotto)', 40),
  ('629813', 'INCASSO PRODOTTI GE – Frigoriferi, Lavelli, Cappe libero posizionamento (con consegna)', 35),
  ('629814', 'INCASSO PRODOTTI GE – Lvs,Lvb, Cappe incas, Forni elett., P. cottura induzione (con consegna)', 35),
  ('629815', 'SOPRALLUOGO per installazioni professionali (senza consegna)', 20),
  ('629816', 'ALLACCIAMENTO RETE IDRICA/ELETTRICA PRODOTTI GRANDI DIMENSIONI (con consegna)', 40),
  ('629817', 'INSTALLAZIONE HOME A/V BASE 3.1 (con consegna)', 30),
  ('629818', 'INSTALLAZIONE HOME A/V FULL 5.1 con canalizzazione esterna (con consegna)', 40),
  ('629819', 'KIT INSTALLAZIONE 2 PRODOTTI DA INCASSO (di cui 1 è un frigo, tutto con consegna)', 55),
  ('630528', 'KIT INSTALLAZIONE 2 PRODOTTI DA INCASSO (no frigo, tutto con consegna)', 55),
  ('651409', 'CONSEGNA BASIC 24H FASCIA 1* (cons. 9-13/14-18 giorno seguente acquisto - ESCLUSI PDT GE e TV >32”)', 15),
  ('707296', 'CONSEGNA COMFORT FASCIA 1* (consegna 9-13/14-18 il giorno seguente all’acquisto) inclusiva di allacciamento', 25),
  ('707298', 'CONSEGNA SERALE FASCIA 1* (consegna 18-21) inclusiva di allacciamento', 28),
  ('723111', 'SUPPLEMENTO GRANDI DIMENSIONI (Combinati-Coreani >400 lt) x codici **', 15),
  ('723112', 'SUPPLEMENTO GRANDI DIMENSIONI FRIGO SIDE BY SIDE/AMERICANI x codici **', 20),
  ('737106', 'INSTALLAZIONE SMART TV (con consegna)', 40),
  ('752267', 'CONSEGNA FASCIA 1* SU APPUNTAMENTO AD ORARIO PREDEFINITO (slot di 1 ora) inclusiva di allacciamento', 30),
  ('20250188', 'CONSEGNA PRODOTTO SUCCESSIVO', 11),
  ('21250224', 'CONSEGNA E ALLACCIAMENTO EXTRA DIMENSIONI (es. Washtower)', 50),
  ('22250209', 'SOPRALLUOGO per consegne e allacciamenti particolari', 18),
  ('23250161', 'CONSEGNA STANDARD FASCIA 1* (consegna 9-13/14-18) senza allacciamento', 22),
  ('23250161', 'RICONSEGNA PER CAUSE INDIPENDENTI DALL’APPALTATORE - (Equivalente al “solo Trasporto”)', 19),
  ('24250191', 'SUPPLEMENTO CONSEGNA FASCIA 2 (in aggiunta a codici CONSEGNA** x distanze da 51 - a 70 km)', 8),
  ('27250174', 'ALLACCIAMENTO PRODOTTO', 3),
  ('28250159', 'INVERSIONE PORTE FRIGORIFERO', 20),
  ('RAEE Trasf', 'Ritiro 1:1 - Trasporto RAEE da PV a LdR/CdR (Se trasporto dedicato) a Bancale', 15),
  ('TCO70', 'TARIFFA CONSEGNA OLTRE I Km 70 Solo Andata', 0.5),
]
# fmt: on


def listino_warnings() -> list[str]:
  """Anomalie del listino che non bloccano l'import ma vanno conosciute."""
  codes = [code for code, _, _ in LISTINO]
  return [
    f'Codice {code} usato da più servizi: get_service_user_by_user_and_code ne risolve uno solo'
    for code in sorted({code for code in codes if codes.count(code) > 1})
  ]


def validate(session) -> list[str]:
  """Precondizioni verificate prima di scrivere, niente insert su dati incoerenti."""
  errors = []

  if not session.query(Company).filter(Company.id == COMPANY_ID).first():
    errors.append(f'Company {COMPANY_ID} inesistente')

  names = [name for _, name, _ in LISTINO]
  for name in sorted({name for name in names if names.count(name) > 1}):
    errors.append(f'Nome servizio duplicato nel listino, a database non sarebbe distinguibile: {name}')

  users = session.query(User).filter(User.id.in_(USER_IDS), User.company_id == COMPANY_ID).all()
  found = {user.id: user for user in users}
  for user_id in USER_IDS:
    user = found.get(user_id)
    if not user:
      errors.append(f'Utente {user_id} inesistente o fuori dalla company {COMPANY_ID}')
    elif user.role != UserRole.CUSTOMER:
      errors.append(f'Utente {user_id} ({user.nickname}) ha ruolo {user.role.value}, atteso Customer')

  return errors


def get_service(session, name: str) -> Service:
  return session.query(Service).filter(Service.company_id == COMPANY_ID, Service.name == name).first()


def get_service_user(session, user_id: int, service_id: int) -> ServiceUser:
  return (
    session.query(ServiceUser)
    .filter(
      ServiceUser.company_id == COMPANY_ID,
      ServiceUser.user_id == user_id,
      ServiceUser.service_id == service_id,
    )
    .first()
  )


def import_listino(session, apply: bool = False) -> dict:
  report = {'services': [], 'created': [], 'updated': []}

  for code, name, price in LISTINO:
    service = get_service(session, name)
    if not service:
      print(f'+ servizio {"creato" if apply else "da creare"}: {name}')
      report['services'].append(name)
      if apply:
        service = create(Service, {'name': name, 'type': OrderType.DELIVERY, 'professional': False}, session=session)

    for user_id in USER_IDS:
      service_user = get_service_user(session, user_id, service.id) if service else None
      if not service_user:
        print(f'  + utente {user_id}: codice {code} a {price}')
        report['created'].append((user_id, code))
        if apply:
          create(
            ServiceUser,
            {'user_id': user_id, 'service_id': service.id, 'code': code, 'price': float(price)},
            session=session,
          )
      elif service_user.code != code or service_user.price != float(price):
        print(f'  ~ utente {user_id}: codice {service_user.code} a {service_user.price} -> {code} a {price}')
        report['updated'].append((user_id, code))
        if apply:
          service_user.code = code
          service_user.price = float(price)

  if apply:
    session.commit()

  return report


def parse_args():
  parser = argparse.ArgumentParser(description=f'Importa il listino MediaMarket per la company {COMPANY_ID}.')
  parser.add_argument(
    '--apply',
    action='store_true',
    help="Applica le scritture. Senza questa opzione viene eseguita solo un'anteprima.",
  )
  return parser.parse_args()


if __name__ == '__main__':
  args = parse_args()
  set_database(os.environ['DATABASE_URL'])

  if not args.apply:
    print('DRY RUN: nessuna modifica al database. Usa --apply per importare il listino.')

  for warning in listino_warnings():
    print(f'! {warning}')

  with scope(company_id=COMPANY_ID), Session() as session:
    errors = validate(session)
    if errors:
      for error in errors:
        print(f'x {error}')
      sys.exit(1)

    result = import_listino(session, apply=args.apply)

  print(
    f'\nServizi: {len(result["services"])} | '
    f'Associazioni nuove: {len(result["created"])} | '
    f'Associazioni aggiornate: {len(result["updated"])}'
  )
