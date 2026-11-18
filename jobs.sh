#!/bin/sh
# Comando del container dei lavori programmati (${SERVICE}-jobs in
# gitlab/deploy.yml, solo in produzione): per sempre, dorme fino al prossimo
# orario e lancia il lavoro che cade a quell'ora. Gli orari sono HH:MM separati
# da spazi, in ora italiana (vedi BACKUP_TZ):
#  - BACKUP_TIMES: `python -m src.backup` (src/backup.py: dump del database e
#    cartella prod verso la macchina di backup);
#  - CHECKS_TIMES: `python -m src.checks` (src/checks.py: report su Telegram
#    dei dati corrotti e dei file che non tornano fra database e cartella).
# Se i due cadono nello stesso minuto, prima il backup e poi i check.
#
# Ogni lavoro gira sotto il suo lock (/tmp/italco-backup.lock e
# /tmp/italco-checks.lock): uno lanciato a mano (docker exec <container> flock
# /tmp/italco-backup.lock python -m src.backup) non si sovrappone a quello
# programmato, e il deploy aspetta che i lock siano liberi prima di togliere il
# container. Un lavoro fallito non ferma il ciclo: si riprova al suo orario dopo.
set -eu

BACKUP_TIMES="${BACKUP_TIMES:-00:00 06:00 12:00 18:00}"
CHECKS_TIMES="${CHECKS_TIMES:-09:15}"
BACKUP_LOCK_FILE=/tmp/italco-backup.lock
CHECKS_LOCK_FILE=/tmp/italco-checks.lock

# Gli orari sono in ora italiana (BACKUP_TZ, default Europe/Rome), non in UTC:
# restano gli stessi anche col cambio dell'ora legale. Senza il file del fuso
# (pacchetto tzdata nell'immagine) date userebbe UTC in silenzio e i lavori
# slitterebbero di una o due ore: meglio fermarsi subito e farlo vedere nel log.
export TZ="${BACKUP_TZ:-Europe/Rome}"
if [ ! -e "/usr/share/zoneinfo/${TZ}" ]; then
  echo "jobs: fuso orario '${TZ}' sconosciuto (manca tzdata nell'immagine?)" >&2
  exit 1
fi

# Prossimo orario (secondi epoch) fra quelli di $2 dopo l'istante $3; $1 e' il
# nome della variabile, per i messaggi. Vuoto se non c'e' nessun orario valido.
next_time() {
  next=""
  for at in $2; do
    case "$at" in
      [0-1][0-9]:[0-5][0-9] | 2[0-3]:[0-5][0-9]) ;;
      *)
        echo "jobs: orario '${at}' non valido in $1 (HH:MM), ignorato" >&2
        continue
        ;;
    esac
    candidate=$(date -d "today ${at}" +%s)
    if [ "$candidate" -le "$3" ]; then
      candidate=$(date -d "tomorrow ${at}" +%s)
    fi
    if [ -z "$next" ] || [ "$candidate" -lt "$next" ]; then
      next=$candidate
    fi
  done
  echo "$next"
}

# $1 nome del lavoro (per il log), $2 lock, $3 modulo python.
run_job() {
  if flock "$2" python -m "$3"; then
    echo "jobs: $1 terminato"
  else
    echo "jobs: $1 fallito, si riprova al prossimo orario" >&2
  fi
}

while :; do
  now=$(date +%s)
  next_backup=$(next_time BACKUP_TIMES "$BACKUP_TIMES" "$now")
  next_checks=$(next_time CHECKS_TIMES "$CHECKS_TIMES" "$now")

  if [ -z "$next_backup" ]; then
    echo "jobs: nessun orario valido in BACKUP_TIMES='${BACKUP_TIMES}'" >&2
    exit 1
  fi
  if [ -z "$next_checks" ]; then
    echo "jobs: nessun orario valido in CHECKS_TIMES='${CHECKS_TIMES}'" >&2
    exit 1
  fi

  next=$next_backup
  if [ "$next_checks" -lt "$next" ]; then
    next=$next_checks
  fi
  due=""
  if [ "$next_backup" -eq "$next" ]; then
    due="backup"
  fi
  if [ "$next_checks" -eq "$next" ]; then
    due="${due:+$due e }checks"
  fi

  echo "jobs: prossimo ${due} alle $(date -d "@${next}" '+%Y-%m-%d %H:%M %Z')"
  sleep $((next - now))

  if [ "$next_backup" -eq "$next" ]; then
    run_job backup "$BACKUP_LOCK_FILE" src.backup
  fi
  if [ "$next_checks" -eq "$next" ]; then
    run_job checks "$CHECKS_LOCK_FILE" src.checks
  fi
done
