#!/usr/bin/env bash
# update.sh — brings paperScraper on the tower up to date and (re)starts its containers.
#
# Usage:
#   ./update.sh           # refuses while the daily check is running
#   ./update.sh --force   # restarts anyway (the running check stops; it is done again tomorrow)
#
# Restarting also closes the web terminal's session, with any search running in it.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" != "--force" ]] \
   && docker compose exec -T daily python -c "import run_lock, sys; sys.exit(not run_lock.daily_check_running())" 2>/dev/null; then
    echo "La revisión diaria está en marcha. Espera a que termine o usa ./update.sh --force."
    exit 1
fi

echo "── Bajando el código ──"
git pull

echo "── Construyendo la imagen ──"
docker compose build

echo "── Arrancando ──"
# The code is mounted, not in the image: without recreating them, the running programs keep the old code.
docker compose up -d --remove-orphans --force-recreate
docker compose ps
