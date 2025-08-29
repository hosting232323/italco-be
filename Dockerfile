# Dockerfile aggiornato
FROM python:3.12-slim

WORKDIR /src

# Installa git e altre dipendenze di base
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Copia i file del progetto
COPY requirements.txt ./
COPY src ./src

# Installa le dipendenze
RUN pip install --upgrade pip && pip install -r requirements.txt

EXPOSE 80

CMD ["python", "-m", "src"]
