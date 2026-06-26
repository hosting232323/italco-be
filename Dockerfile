FROM python:3.11-slim

WORKDIR /app

ENV TZ=Europe/Rome

RUN apt-get update && apt-get install -y \
  tzdata \
  git \
  gcc \
  libpq-dev \
  postgresql-client \
  rsync \
  restic \
  pkg-config \
  libcairo2-dev \
  openssh-client \
  curl \
  && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
  && echo $TZ > /etc/timezone \
  && rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb \
  && dpkg -i /tmp/cloudflared.deb \
  && rm /tmp/cloudflared.deb

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY . .

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "--access-logfile", "-", "--error-logfile", "-", "src.__main__:app"]
