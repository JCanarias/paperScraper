#!/usr/bin/env bash
# Serves the menu as a terminal in the browser (ttyd), only to this machine (cloudflared brings it out).
# Everything runs inside tmux: closing the page or losing the connection doesn't stop a search,
# and opening the page again shows it where it was.
HERE="$(cd "$(dirname "$0")" && pwd)"
PORT="${PAPERSCRAPER_WEB_PORT:-7681}"

# ttyd 1.7 and later are read-only unless told otherwise; the older ones don't know that option.
WRITABLE=()
if ttyd --help 2>&1 | grep -q -- "--writable"; then
    WRITABLE=(--writable)
fi

exec ttyd --port "$PORT" --interface lo --check-origin "${WRITABLE[@]}" \
    -t titleFixed=paperScraper -t fontSize=15 \
    tmux -u -f "$HERE/tmux.conf" new-session -A -s paperscraper "bash $HERE/menu.sh"
