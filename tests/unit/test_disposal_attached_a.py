from pathlib import Path
from types import SimpleNamespace

from flask import Flask, render_template

from src.end_points.exportation import disposal as disposal_module


def _rae_product_row():
  return (
    SimpleNamespace(number=12, quantity=2, disposal_id=7),
    SimpleNamespace(name='Frigorifero', cer_code=200123, group_code='R1'),
    SimpleNamespace(id=10, nickname='Punto vendita Bari'),
    SimpleNamespace(id=4, addressee='Mario Rossi'),
  )


def test_export_attached_a_builds_afir_code_from_user_and_disposal_ids(monkeypatch):
  rendered = {}

  def capture_template(template, **context):
    rendered.update(template=template, **context)
    return '<html></html>'

  class PdfStatus:
    err = False

  monkeypatch.setattr(disposal_module, 'get_disposal_for_export', lambda _id: {'code': 37})
  monkeypatch.setattr(disposal_module, 'get_disposal_rae_products', lambda _id: [_rae_product_row()])
  monkeypatch.setattr(disposal_module, 'get_schedule_by_order', lambda _id: None)
  monkeypatch.setattr(disposal_module, 'render_template', capture_template)
  monkeypatch.setattr(disposal_module.pisa, 'CreatePDF', lambda **_kwargs: PdfStatus())
  monkeypatch.setattr(disposal_module, 'export_pdf', lambda content: content)

  disposal_module.export_disposal_attached_a(7)

  assert rendered['template'] == 'disposal_attached_a.html'
  assert rendered['rows'][0]['codice_afir'] == '10-AFIR-7'


def test_afir_column_is_rendered_only_in_attached_a():
  template_folder = Path(__file__).resolve().parents[2] / 'templates'
  app = Flask(__name__, template_folder=str(template_folder))
  row = {
    'dtr': '01/07/2026',
    'n_ddt': 12,
    'nome_prodotto': 'Frigorifero',
    'codice_cer': 200123,
    'raggruppamento': 'R1',
    'quantita': 2,
    'cliente': 'Punto vendita Bari',
    'destinatario': 'Mario Rossi',
    'codice_afir': '10-AFIR-7',
  }
  disposal = {
    'code': 37,
    'date': '01/07/2026',
    'carrier': {'company_name': 'Trasportatore'},
    'collection_center': {'company_name': 'Centro raccolta'},
  }

  with app.app_context():
    attached_a = render_template('disposal_attached_a.html', disposal=disposal, rows=[row], total=2)
    card_index = render_template(
      'disposal_card_index.html',
      disposal=disposal,
      customers=[{'nome': 'PV Bari', 'rae_products': [row], 'subtotale': 2}],
      total=2,
    )

  assert attached_a.count('Codice AFIR') == 1
  assert attached_a.count('10-AFIR-7') == 1
  assert '<td class="label">Codice AFIR</td>' in attached_a
  assert '>Codice AFIR</th>' not in attached_a
  assert 'Codice AFIR' not in card_index
  assert '10-AFIR-7' not in card_index
