#!/bin/bash
# The demo database back to the state before a section: ./restore.sh 01   (the snapshot aryapack_s01)
# Run where the docker-compose.yml of the trial is (TRIAL=... to give its folder).
set -e
cd "${TRIAL:-.}"
docker compose stop odoo >/dev/null
docker compose exec -T db dropdb -U odoo --if-exists aryapack
docker compose exec -T db createdb -U odoo -T aryapack_s$1 aryapack
docker compose up -d odoo >/dev/null
sleep 8
echo "aryapack is as before section $1"
