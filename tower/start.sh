#!/usr/bin/env bash
# Serves the menu as a terminal in the browser, only to this machine (cloudflared brings it out).
# Everything runs inside tmux: closing the page or losing the connection doesn't stop a search,
# and opening the page again shows it where it was.
#
# ttyd shows the terminal, but listens only on a UNIX socket inside the container; web_login.py is
# the door on localhost:7681 (a login page and a cookie, which works on phones too).
HERE="$(cd "$(dirname "$0")" && pwd)"
export TTYD_SOCKET="${TTYD_SOCKET:-/tmp/ttyd.sock}"

# The browser asks for this user and password. Without them the terminal doesn't start:
# it would be open to anyone who finds the address.
if [ -z "${PAPERSCRAPER_WEB_USER:-}" ] || [ -z "${PAPERSCRAPER_WEB_PASSWORD:-}" ]; then
    echo "Faltan PAPERSCRAPER_WEB_USER y PAPERSCRAPER_WEB_PASSWORD en .env; la terminal web no arranca." >&2
    exit 1
fi

# ttyd 1.7 and later are read-only unless told otherwise; the older ones don't know that option.
WRITABLE=()
if ttyd --help 2>&1 | grep -q -- "--writable"; then
    WRITABLE=(--writable)
fi

rm -f "$TTYD_SOCKET"
ttyd --interface "$TTYD_SOCKET" "${WRITABLE[@]}" \
    -t titleFixed=paperScraper -t fontSize=15 -t disableLeaveAlert=true \
    tmux -u -f "$HERE/tmux.conf" new-session -A -s paperscraper "bash $HERE/menu.sh" &
"${PYTHON:-python}" "$HERE/web_login.py" &

# If either stops, the container stops too, and Docker starts it again.
wait -n
exit 1
