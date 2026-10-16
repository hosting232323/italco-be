FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
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
  && rm -rf /var/lib/apt/lists/*

RUN curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb \
  && dpkg -i /tmp/cloudflared.deb \
  && rm /tmp/cloudflared.deb

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# generic_lib e' una dipendenza git senza versione: il layer qui sopra resta in
# cache finche' pyproject.toml non cambia, quindi la lib va riallineata a parte.
# LIB_REF e' lo sha di HEAD di generic-lib (lo risolve il job di deploy): se la
# lib non e' cambiata il layer e' in cache, altrimenti viene reinstallata.
ARG LIB_REF=HEAD
RUN pip install --no-cache-dir --upgrade --upgrade-strategy only-if-needed   "generic_lib[unix] @ git+https://github.com/hosting232323/generic-lib.git@${LIB_REF}"

COPY . .

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "--access-logfile", "-", "--error-logfile", "-", "src.__main__:app"]
