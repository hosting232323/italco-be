import pandas as pd
from io import BytesIO

from .utils import export_excel
from ...database.schema import User
from ..orders.queries import query_orders, format_query_result


def export_orders_excel(user: User, order_ids: list):
  if not order_ids:
    return {'status': 'ko', 'error': 'Nessun ordine selezionato'}

  orders = []
  for tupla in query_orders(user, [{'model': 'Order', 'field': 'id', 'value': order_ids}]):
    orders = format_query_result(tupla, orders, user)
  if not orders:
    return {'status': 'ko', 'error': 'Nessun ordine trovato'}

  rows = []
  for o in orders:
    prodotti = ', '.join(o.get('products', {}).keys())
    servizi_list = []
    for prod_data in o.get('products', {}).values():
      for s in prod_data.get('services', []):
        if isinstance(s, dict):
          nome = s.get('name') or s.get('title') or str(s)
        else:
          nome = str(s)
        servizi_list.append(nome)
    servizi = ', '.join(servizi_list)

    rows.append(
      {
        'ID Ordine': o['id'],
        'Destinatario': o.get('addressee', ''),
        'Indirizzo': o.get('address', ''),
        'CAP': o.get('cap', ''),
        'Stato': o.get('status', ''),
        'Tipo': o.get('type', ''),
        'Data Prevista Consegna': str(o.get('dpc', '') or ''),
        'Data Richiesta Consegna': str(o.get('drc', '') or ''),
        'Data Prenotazione': str(o.get('booking_date', '') or ''),
        'Prodotti': prodotti,
        'Servizi': servizi,
        'Note Cliente': o.get('customer_note', '') or '',
        'Note Operatori': o.get('operator_note', '') or '',
        'Anomalia': 'Si' if o.get('anomaly') else 'No',
        'Ritardo': 'Si' if o.get('delay') else 'No',
        'Punto Vendita': o.get('user', {}).get('name', '') if isinstance(o.get('user'), dict) else '',
      }
    )

  df = pd.DataFrame(rows)
  output = BytesIO()
  with pd.ExcelWriter(output, engine='openpyxl') as writer:
    df.to_excel(writer, index=False, sheet_name='Ordini')
    worksheet = writer.sheets['Ordini']
    for col_idx, col in enumerate(df.columns, 1):
      max_len = max(df[col].astype(str).map(len).max(), len(col)) + 4
      worksheet.column_dimensions[worksheet.cell(1, col_idx).column_letter].width = min(max_len, 50)
  output.seek(0)
  return export_excel(output.getvalue())
