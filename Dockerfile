# paperScraper on the tower: the menu as a web terminal, and the daily check (docker-compose.yml).
# The code isn't copied: it is mounted (.:/app), so a `git pull` and a restart are enough.
FROM python:3.11-slim-bookworm

# Google Chrome (Sci-Hub), an invisible screen for it (Xvfb) and the web terminal (ttyd + tmux).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
    | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
    > /etc/apt/sources.list.d/google-chrome.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends google-chrome-stable xvfb ttyd tmux tzdata \
 && rm -rf /var/lib/apt/lists/*

# The same user id as the tower's user, so the files written in library/ and data/ are theirs.
ARG UID=1000
ARG GID=1000
RUN groupadd -g "$GID" app && useradd -m -u "$UID" -g "$GID" app

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHON=python \
    PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    TZ=Europe/Madrid \
    CHROME_IN_CONTAINER=1
USER app
ENTRYPOINT ["sh", "/app/tower/entrypoint.sh"]
