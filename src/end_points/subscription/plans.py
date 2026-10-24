# Abbonamento: un solo prezzo mensile per attività, deciso dal super admin
# (Company.subscription_price_cents). Checkout lo riceve inline (price_data),
# quindi non serve creare prodotti né Price id nella dashboard Stripe.
CURRENCY = 'eur'
INTERVAL = 'month'

# Minimo addebitabile da Stripe in euro.
MIN_PRICE_CENTS = 50
