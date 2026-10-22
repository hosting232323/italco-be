# Piani di abbonamento. Prezzi segnaposto, giusti per far funzionare il flusso:
# Checkout li riceve inline (price_data), quindi non serve creare prodotti né
# Price id nella dashboard Stripe. Quando i prezzi veri saranno decisi basta
# cambiare questa tabella (o passare a Price id veri).
PLANS = {
  'base': {'name': 'Base', 'description': 'Per iniziare', 'amount': 2900},
  'pro': {'name': 'Pro', 'description': 'Per le attività in crescita', 'amount': 7900},
  'business': {'name': 'Business', 'description': 'Per volumi elevati', 'amount': 14900},
}

CURRENCY = 'eur'
INTERVAL = 'month'


def public_plans() -> list[dict]:
  return [{'id': plan_id, **plan, 'currency': CURRENCY, 'interval': INTERVAL} for plan_id, plan in PLANS.items()]
