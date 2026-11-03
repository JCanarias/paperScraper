#!/usr/bin/env bash
# Prepares the tower: dependencies, the menu's virtualenv and the service. Run it from the repo root:
#     bash tower/install.sh
# It doesn't touch cloudflared or Calibre; see tower/README.md for those steps.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Programas del sistema (ttyd, tmux)"
sudo apt-get update
sudo apt-get install -y ttyd tmux python3-venv

echo "== Entorno de Python"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

chmod +x tower/menu.sh tower/start.sh

echo "== Servicios: la terminal web y la revisión diaria de las 6:00"
sudo cp tower/paperscraper-web.service tower/paperscraper-daily.service tower/paperscraper-daily.timer \
    /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now paperscraper-web
sudo systemctl enable --now paperscraper-daily.timer
systemctl --no-pager status paperscraper-web | head -5
systemctl --no-pager list-timers paperscraper-daily.timer

if [ ! -f telegram_bot/.env ]; then
    echo "AVISO: falta telegram_bot/.env; la revisión diaria no podrá avisar por Telegram."
fi

if [ ! -f .env ]; then
    echo "AVISO: falta .env (cópialo desde el PC y pon CALIBRE_URL=http://localhost:8080)."
fi
if ! command -v google-chrome >/dev/null && ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
    echo "AVISO: no hay Chrome instalado; Sci-Hub lo necesita."
fi
echo "Listo. Pruébalo en la torre: http://localhost:7681"
