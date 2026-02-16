FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git gcc libpq-dev pkg-config libcairo2-dev python3-dev build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "--access-logfile", "-", "--error-logfile", "-", "src.__main__:app"]
