"""Carta intestata dei PDF (templates/components/company.html).

Il macro company_header stampa in cima a ogni documento un rettangolo con
logo, dati legali dell'attività e la targhetta "Powered by Ares Logistics",
che è un SVG perché xhtml2pdf non sa arrotondare gli angoli in CSS.
È tutto guardato: senza company non stampa nulla; senza logo dell'attività
ripiega su quello di Ares.
"""

import base64

from flask import render_template_string

from src.end_points.exportation.utils import get_company_logo, get_powered_tag

from tests.unit.factories import create_company


TEMPLATE = (
  '{% from "components/company.html" import company_header %}{{ company_header(company, company_logo, powered_tag) }}'
)


def _render(app, **context):
  with app.test_request_context():
    return render_template_string(TEMPLATE, **context)


def test_letterhead_shows_identity_vat_and_tax_code_on_one_line(app, db):
  company = create_company(
    legal_name='ACME Logistica SRL',
    vat_number='12345678901',
    tax_code='ACMLGS80A01H501Z',
    address='Via Roma 1',
    city='Bari (BA)',
  )

  html = _render(
    app,
    company=company,
    company_logo='data:image/png;base64,AAAA',
    powered_tag='data:image/svg+xml;base64,BBBB',
  )

  assert 'ACME Logistica SRL' in html
  assert 'Via Roma 1, Bari (BA)' in html
  assert 'P. IVA 12345678901 - C.F. ACMLGS80A01H501Z' in html
  assert 'Albo Gestori' not in html
  assert 'src="data:image/png;base64,AAAA"' in html
  assert 'src="data:image/svg+xml;base64,BBBB"' in html


def test_letterhead_falls_back_to_name_and_hides_empty_fields(app, db):
  company = create_company(name='Solo Nome', vat_number='99988877766')

  html = _render(app, company=company, company_logo=None, powered_tag=None)

  assert 'Solo Nome' in html
  assert 'P. IVA 99988877766' in html
  assert 'C.F.' not in html
  assert 'Albo Gestori' not in html


def test_letterhead_without_company_renders_nothing(app, db):
  assert _render(app, company=None, company_logo=None, powered_tag=None).strip() == ''


def test_company_logo_falls_back_to_ares_when_none_uploaded(db):
  data_uri = get_company_logo(create_company())

  assert data_uri.startswith('data:image/png;base64,')
  assert len(data_uri) > 200


def test_powered_tag_is_an_svg_with_the_ares_wording():
  data_uri = get_powered_tag()

  assert data_uri.startswith('data:image/svg+xml;base64,')
  svg = base64.b64decode(data_uri.split('base64,')[1]).decode('utf-8')
  assert 'Powered by' in svg and 'Ares Logistics' in svg
