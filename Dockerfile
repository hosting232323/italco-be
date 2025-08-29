# Dockerfile
FROM python:3.12-slim

# Imposta la working directory
WORKDIR /src

# Copia i file del progetto
COPY requirements.txt ./
COPY src ./src

# Installa le dipendenze
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Espone la porta su cui il backend gira
EXPOSE 80

# Comando per partire
CMD ["python", "-m", "src"]
