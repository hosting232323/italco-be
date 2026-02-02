import os
import pandas as pd
from sqlalchemy import and_
from src.database.schema import ServiceUser
from database_api import set_database, Session
from database_api.operations import update, create


user_ids = [1,2,3,4]


def get_excel_data():
  df = pd.read_excel('Listino Coppola est.xls')

  col_codice = df.columns[1]
  col_id_servizi = df.columns[6]
  
  df[col_codice] = pd.to_numeric(df[col_codice], errors='coerce')
  df[col_id_servizi] = pd.to_numeric(df[col_id_servizi], errors='coerce')

  df_validi = df.dropna(subset=[col_codice, col_id_servizi])
  return [
    {
      'code': int(row[col_codice]),
      'service_id': int(row[col_id_servizi])
    }
    for _, row in df_validi.iterrows()
  ]


def get_service_user(user_id: int, service_id: int) -> ServiceUser:
  with Session() as session:
    return session.query(ServiceUser).filter(
      and_(
        ServiceUser.user_id == user_id,
        ServiceUser.service_id == service_id
      )
    ).first()


if __name__ == '__main__':
  set_database(os.environ['DATABASE_URL'])
  
  datas = get_excel_data()
  created = []
  for user in user_ids:
    for data in datas:
      service_user = get_service_user(user, data['service_id'])
      print(service_user)
      if not service_user:
        created.append(create(ServiceUser, {
          'code': data['code'],
          'price': 10,
          'user_id': user,
          'service_id': data['service_id']
        }))
      else:
        update(service_user, {
          'code': data['code']
        })
  print(created)
