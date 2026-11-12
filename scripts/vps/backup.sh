#!/usr/bin/env bash
# Respaldo cifrado de CAPITAL RADAR PRO (Postgres + volumen de datos). Ejecutar en el VPS desde /opt/capital-radar.
# La clave de cifrado del respaldo viene de BACKUP_PASSPHRASE_FILE (fuera del repo, chmod 600).
set -euo pipefail
cd "$(dirname "$0")/../.."
DEST=${BACKUP_DIR:-/var/backups/capital-radar}
PASS=${BACKUP_PASSPHRASE_FILE:-/opt/capital-radar-secrets/backup.pass}
TS=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$DEST"; chmod 700 "$DEST"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
docker compose exec -T db pg_dump -U radar -d radar -Fc > "$TMP/radar.pgdump"
docker run --rm -v capital-radar_appdata:/data -v "$TMP":/out alpine tar czf /out/appdata.tgz -C /data .
tar czf "$TMP/bundle.tgz" -C "$TMP" radar.pgdump appdata.tgz
openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -in "$TMP/bundle.tgz" -out "$DEST/radar-$TS.tgz.enc" -pass file:"$PASS"
( cd "$DEST" && sha256sum "radar-$TS.tgz.enc" > "radar-$TS.tgz.enc.sha256" )
# verificación de recuperabilidad: descifra y lista el contenido
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in "$DEST/radar-$TS.tgz.enc" -pass file:"$PASS" | tar tz | sed 's/^/  contiene: /'
find "$DEST" -name 'radar-*.enc*' -mtime +14 -delete
echo "OK $DEST/radar-$TS.tgz.enc"
