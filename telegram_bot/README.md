# Bot de Telegram para guardar archivos

Guarda en `TELEGRAM_DOWNLOAD_DIR` los documentos de texto que le mandes (pdf, epub, mobi, azw/azw3, kfx, fb2, djvu, txt, md, rtf, doc/docx, odt, html, tex).
Rechaza el resto (mp3, mp4, fotos, zip...). La lista se puede cambiar con `TELEGRAM_ALLOWED_EXTENSIONS`.
Solo responde a los usuarios cuyo id esté en `TELEGRAM_ALLOWED_USER_IDS`.

## Puesta en marcha (en la torre Linux)

1. Crea el bot con [@BotFather](https://t.me/BotFather) (`/newbot`) y copia el token.
2. Instala dependencias:
   ```bash
   cd ~/paperScraper
   python3 -m venv .venv
   .venv/bin/pip install -r telegram_bot/requirements.txt
   ```
3. Configura:
   ```bash
   cp telegram_bot/.env.example telegram_bot/.env
   nano telegram_bot/.env   # token y carpeta de destino
   ```
4. Arráncalo (`.venv/bin/python telegram_bot/bot.py`), mándale `/start` desde el móvil:
   te responderá con tu id. Ponlo en `TELEGRAM_ALLOWED_USER_IDS` y reinicia el bot.

## Que arranque solo con la torre (systemd)

```bash
sudo cp telegram_bot/telegram-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/telegram-bot.service   # ajusta User y rutas
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-bot
journalctl -u telegram-bot -f   # ver logs
```

## Archivos de más de 20 MB

La API pública de Telegram no deja que los bots descarguen archivos de más de 20 MB.
Para quitar ese límite (hasta 2 GB) hay que levantar un servidor
[telegram-bot-api](https://github.com/tdlib/telegram-bot-api) local en la misma torre, por ejemplo con Docker:

```bash
docker run -d --name tg-bot-api --restart unless-stopped -p 8081:8081 \
  -e TELEGRAM_API_ID=<api_id> -e TELEGRAM_API_HASH=<api_hash> \
  -e TELEGRAM_LOCAL=1 \
  -v /var/lib/telegram-bot-api:/var/lib/telegram-bot-api \
  aiogram/telegram-bot-api:latest
```

(`api_id` y `api_hash` se sacan en https://my.telegram.org.) Antes de usarlo, cierra la sesión del bot en la
API pública una vez: `curl https://api.telegram.org/bot<TOKEN>/logOut`. Después pon
`TELEGRAM_LOCAL_API_URL=http://localhost:8081` en el `.env`.

El usuario que ejecuta el bot necesita permiso de lectura sobre `/var/lib/telegram-bot-api`,
porque en modo local el bot copia los archivos directamente desde ahí.
