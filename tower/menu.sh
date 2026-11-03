#!/usr/bin/env bash
# The terminal shown in the browser: main.py's menu, again and again.
# main.py does one thing and ends, as when it is run by hand; then this waits for Enter and starts it again.
cd "$(dirname "$0")/.." || exit 1
export PYTHONIOENCODING=utf-8

while true; do
    clear
    "${PYTHON:-.venv/bin/python}" main.py
    echo
    read -r -p "Pulsa Enter para volver al menú... " _
done
