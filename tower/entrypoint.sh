#!/bin/sh
# Every container starts here: Chrome (Sci-Hub) needs a screen, and Xvfb gives it an invisible one.
rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1366x900x24 -nolisten tcp >/dev/null 2>&1 &
export DISPLAY=:99
exec "$@"
