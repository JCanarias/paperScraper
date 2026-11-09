"""Sends messages to the user through the Telegram bot (the one in telegram_bot/).

It uses the bot's own settings (telegram_bot/.env): its token, and the allowed users as recipients.
A message that can't be sent is reported on screen; it never stops the program.
"""
import json
from pathlib import Path

import requests
from dotenv import dotenv_values

BOT_SETTINGS = Path(__file__).parent / "telegram_bot" / ".env"
PUBLIC_API_URL = "https://api.telegram.org"
TIMEOUT_SECONDS = 30
# Telegram doesn't accept longer messages.
MAX_MESSAGE_LENGTH = 4096


def send_message(text: str, buttons: list[tuple[str, str]] | None = None) -> bool:
    """Send `text` to the allowed users; True if it reached them.

    `buttons` are (label, data) pairs shown under the message in one row; when one is pressed,
    the bot (telegram_bot/bot.py) gets its data.
    """
    settings = dotenv_values(BOT_SETTINGS) if BOT_SETTINGS.exists() else {}
    token = (settings.get("TELEGRAM_BOT_TOKEN") or "").strip()
    recipients = [user_id.strip() for user_id in (settings.get("TELEGRAM_ALLOWED_USER_IDS") or "").split(",")
                  if user_id.strip()]
    if not token or not recipients:
        print(f"Aviso: no se puede avisar por Telegram (falta el token o el usuario en {BOT_SETTINGS}).")
        return False
    # When the bot uses its own Bot API server, the public one no longer answers for it.
    api_url = (settings.get("TELEGRAM_LOCAL_API_URL") or "").strip().rstrip("/") or PUBLIC_API_URL
    data = {"text": text[:MAX_MESSAGE_LENGTH], "disable_web_page_preview": "true"}
    if buttons:
        data["reply_markup"] = json.dumps(
            {"inline_keyboard": [[{"text": label, "callback_data": value} for label, value in buttons]]})
    sent = False
    for chat_id in recipients:
        try:
            response = requests.post(f"{api_url}/bot{token}/sendMessage", data={"chat_id": chat_id, **data},
                                     timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            sent = True
        except requests.RequestException as error:
            # The error text would show the token (it is in the address), so only the type is shown.
            print(f"Aviso: no se ha podido mandar el mensaje de Telegram ({type(error).__name__}).")
    return sent
