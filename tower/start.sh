#!/usr/bin/env bash
# Serves the menu as a terminal in the browser (ttyd), only to this machine (cloudflared brings it out).
# Everything runs inside tmux: closing the page or losing the connection doesn't stop a search,
# and opening the page again shows it where it was.
HERE="$(cd "$(dirname "$0")" && pwd)"
PORT="${PAPERSCRAPER_WEB_PORT:-7681}"

# The browser asks for this user and password, as Calibre's server does. Without them the terminal
# doesn't start: it would be open to anyone who finds the address.
if [ -z "${PAPERSCRAPER_WEB_USER:-}" ] || [ -z "${PAPERSCRAPER_WEB_PASSWORD:-}" ]; then
    echo "Faltan PAPERSCRAPER_WEB_USER y PAPERSCRAPER_WEB_PASSWORD en .env; la terminal web no arranca." >&2
    exit 1
fi
case "$PAPERSCRAPER_WEB_USER" in
    *:*) echo "PAPERSCRAPER_WEB_USER no puede llevar ':'." >&2; exit 1 ;;
esac

# ttyd 1.7 and later are read-only unless told otherwise; the older ones don't know that option.
WRITABLE=()
if ttyd --help 2>&1 | grep -q -- "--writable"; then
    WRITABLE=(--writable)
fi

exec ttyd --port "$PORT" --interface lo --check-origin "${WRITABLE[@]}" \
    --credential "$PAPERSCRAPER_WEB_USER:$PAPERSCRAPER_WEB_PASSWORD" \
    -t titleFixed=paperScraper -t fontSize=15 \
    tmux -u -f "$HERE/tmux.conf" new-session -A -s paperscraper "bash $HERE/menu.sh"
