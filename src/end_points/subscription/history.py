from datetime import datetime, timezone


# Storico dei pagamenti di un'attività, ricavato da fatture e abbonamenti di Stripe
# (che restano la fonte di verità: nessuna copia nel DB da tenere allineata).

# Una fattura aperta o non riscossa è un pagamento che non è andato a buon fine.
UNPAID_STATUSES = ('open', 'uncollectible')


def _iso(timestamp: int | None) -> str | None:
  if not timestamp:
    return None
  return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None).isoformat()


def serialize_invoice(invoice) -> dict:
  paid = invoice['status'] == 'paid'
  return {
    'id': invoice['id'],
    'number': invoice.get('number'),
    'status': invoice['status'],
    'amount_cents': invoice.get('amount_paid' if paid else 'amount_due') or 0,
    'created': _iso(invoice.get('created')),
    'paid_at': _iso((invoice.get('status_transitions') or {}).get('paid_at')) if paid else None,
    'attempts': invoice.get('attempt_count') or 0,
    'url': invoice.get('hosted_invoice_url'),
  }


def serialize_subscription_record(subscription) -> dict:
  items = (subscription.get('items') or {}).get('data') or []
  price = (items[0].get('price') or {}) if items else {}
  return {
    'id': subscription['id'],
    'status': subscription['status'],
    'created': _iso(subscription.get('created')),
    'ended_at': _iso(subscription.get('ended_at') or subscription.get('canceled_at')),
    'price_cents': price.get('unit_amount'),
  }


def summarize(invoices: list[dict]) -> dict:
  """Il quadro d'insieme: da quando paga e se ha sempre saldato correttamente.

  "Regolare" = almeno un pagamento, nessuna fattura insoluta e nessuna saldata
  solo dopo un nuovo tentativo.
  """
  paid = [invoice for invoice in invoices if invoice['status'] == 'paid']
  unpaid = [invoice for invoice in invoices if invoice['status'] in UNPAID_STATUSES]
  retried = [invoice for invoice in paid if invoice['attempts'] > 1]
  first = min((invoice['paid_at'] or invoice['created'] for invoice in paid), default=None)
  return {
    'customer_since': first,
    'paid_count': len(paid),
    'paid_total_cents': sum(invoice['amount_cents'] for invoice in paid),
    'unpaid_count': len(unpaid),
    'retried_count': len(retried),
    'regular': bool(paid) and not unpaid and not retried,
  }


def build_history(subscriptions: list, invoices: list) -> dict:
  # Le bozze non sono ancora addebiti: non fanno storico.
  serialized = [serialize_invoice(invoice) for invoice in invoices if invoice['status'] != 'draft']
  return {
    'subscriptions': [serialize_subscription_record(subscription) for subscription in subscriptions],
    'invoices': serialized,
    'summary': summarize(serialized),
  }
