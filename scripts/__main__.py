import pandas as pd


if __name__ == '__main__':
  df = pd.read_excel('Listino Coppola est.xls')

  col_codice = df.columns[1]
  col_id_servizi = df.columns[6]
  
  df[col_codice] = pd.to_numeric(df[col_codice], errors='coerce')
  df[col_id_servizi] = pd.to_numeric(df[col_id_servizi], errors='coerce')

  df_validi = df.dropna(subset=[col_codice, col_id_servizi])
  risultato = [
    {
      'codice': int(row[col_codice]),
      'id_servizio': int(row[col_id_servizi])
    }
    for _, row in df_validi.iterrows()
  ]

  print(risultato)