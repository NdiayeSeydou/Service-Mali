#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
COMPOSE_ENV_FILE="${COMPOSE_ENV_FILE:-.env.prod}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
DB_TMP="$BACKUP_DIR/db-$STAMP.dump.partial"
MEDIA_TMP="$BACKUP_DIR/media-$STAMP.tar.gz.partial"
PRIVATE_TMP="$BACKUP_DIR/private-$STAMP.tar.gz.partial"
trap 'rm -f "$DB_TMP" "$MEDIA_TMP" "$PRIVATE_TMP"' EXIT

compose() {
  docker compose --env-file "$COMPOSE_ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$DB_TMP"
compose exec -T backend tar -czf - --numeric-owner -C /app/media . > "$MEDIA_TMP"
compose exec -T backend tar -czf - --numeric-owner -C /app/private_uploads . > "$PRIVATE_TMP"
mv "$DB_TMP" "$BACKUP_DIR/db-$STAMP.dump"
mv "$MEDIA_TMP" "$BACKUP_DIR/media-$STAMP.tar.gz"
mv "$PRIVATE_TMP" "$BACKUP_DIR/private-$STAMP.tar.gz"
(
  cd "$BACKUP_DIR"
  sha256sum "db-$STAMP.dump" "media-$STAMP.tar.gz" "private-$STAMP.tar.gz" > "sha256-$STAMP.txt"
)
find "$BACKUP_DIR" -maxdepth 1 -type f -mtime "+$BACKUP_RETENTION_DAYS" -delete
printf 'Sauvegarde terminée : %s\n' "$STAMP"
