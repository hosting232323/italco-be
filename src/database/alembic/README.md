# Instruzioni all'uso di Alembic

## Generazione di una migrazione

```bash
alembic revision --autogenerate -m 'Creazione modelli utente'
```

## Allineamento all'ultima migrazione

```bash
alembic upgrade heads
```

## Secuzione di una migrazione

```bash
alembic upgrade +1
```

## Roll back di una migrazione

```bash
alembic downgrade -1
```
