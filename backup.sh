#!/bin/sh
# Comando del container di backup (${SERVICE}-backup in gitlab/deploy.yml,
# solo in produzione): per sempre, dorme fino al prossimo orario di
# BACKUP_TIMES (HH:MM separati da spazi, UTC, l'orologio del container) e
# lancia `python -m src.backup` (src/backup.py: dump del database e cartella
# prod verso la macchina di backup).
#
# Il backup gira sotto il lock /tmp/italco-backup.lock: uno lanciato a mano
# (docker exec <container> flock /tmp/italco-backup.lock python -m src.backup)
# non si sovrappone a quello programmato, e il deploy aspetta che il lock sia
# libero prima di togliere il container. Un backup fallito (che generic-lib
# segnala gia' su Telegram) non ferma il ciclo: si riprova all'orario dopo.
set -eu

BACKUP_TIMES="${BACKUP_TIMES:-05:00 11:00 17:00 23:00}"
LOCK_FILE=/tmp/italco-backup.lock

while :; do
  now=$(date -u +%s)
  next=""
  for at in $BACKUP_TIMES; do
    case "$at" in
      [0-1][0-9]:[0-5][0-9] | 2[0-3]:[0-5][0-9]) ;;
      *)
        echo "backup: orario '${at}' non valido in BACKUP_TIMES (HH:MM), ignorato" >&2
        continue
        ;;
    esac
    candidate=$(date -u -d "today ${at}" +%s)
    if [ "$candidate" -le "$now" ]; then
      candidate=$(date -u -d "tomorrow ${at}" +%s)
    fi
    if [ -z "$next" ] || [ "$candidate" -lt "$next" ]; then
      next=$candidate
    fi
  done

  if [ -z "$next" ]; then
    echo "backup: nessun orario valido in BACKUP_TIMES='${BACKUP_TIMES}'" >&2
    exit 1
  fi

  echo "backup: prossimo alle $(date -u -d "@${next}" '+%Y-%m-%d %H:%M') UTC"
  sleep $((next - now))
  flock "$LOCK_FILE" python -m src.backup || echo "backup: fallito, si riprova al prossimo orario" >&2
done
