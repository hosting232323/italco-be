FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y git build-essential && rm -rf /var/lib/apt/lists/*

COPY ./src ./src

EXPOSE 8080

CMD ["python", "-m", "src"]
