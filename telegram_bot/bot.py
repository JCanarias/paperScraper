"""Telegram bot that saves the text documents it receives (pdf, epub, mobi...) into a local folder.

Run with:  python telegram_bot/bot.py   (from the repo root)
"""
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Read the variables defined in the .env file next to this one.
load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DOWNLOAD_DIR = Path(os.environ["TELEGRAM_DOWNLOAD_DIR"]).expanduser()
# Comma-separated Telegram user ids allowed to use the bot. Empty = nobody.
ALLOWED_USER_IDS = {
    int(uid) for uid in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if uid.strip()
}
# Optional: URL of a self-hosted Bot API server (lifts the 20 MB download limit).
LOCAL_API_URL = os.environ.get("TELEGRAM_LOCAL_API_URL", "").rstrip("/")

# Only documents that contain text (books, papers, notes) are accepted.
DEFAULT_EXTENSIONS = (
    "pdf,epub,mobi,azw,azw3,kfx,fb2,djvu,txt,md,rtf,doc,docx,odt,html,htm,tex"
)
ALLOWED_EXTENSIONS = {
    "." + ext.strip().lower().lstrip(".")
    for ext in os.environ.get("TELEGRAM_ALLOWED_EXTENSIONS", DEFAULT_EXTENSIONS).split(",")
    if ext.strip()
}

CLOUD_API_MAX_BYTES = 20 * 1024 * 1024

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("telegram_bot")


def safe_filename(name: str) -> str:
    """Strip path separators and characters that are awkward on Linux/Windows."""
    name = Path(name).name
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return name or "file"


def unique_path(directory: Path, name: str) -> Path:
    """Return directory/name, adding ' (1)', ' (2)'... if it already exists."""
    path = directory / name
    stem, suffix = path.stem, path.suffix
    counter = 1
    while path.exists():
        path = directory / f"{stem} ({counter}){suffix}"
        counter += 1
    return path


def is_allowed(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id in ALLOWED_USER_IDS


def allowed_list() -> str:
    return ", ".join(sorted(ext.lstrip(".") for ext in ALLOWED_EXTENSIONS))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if message is None or user is None:
        return
    if not is_allowed(update):
        # Show the id so the owner can add it to TELEGRAM_ALLOWED_USER_IDS.
        await message.reply_text(f"No autorizado. Tu id de usuario es: {user.id}")
        log.warning("Unauthorized /start from %s (%s)", user.id, user.username)
        return
    await message.reply_text(
        f"Listo. Mándame documentos ({allowed_list()}) y los guardaré en:\n{DOWNLOAD_DIR}"
    )


async def reject_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or not is_allowed(update):
        return
    await message.reply_text(
        f"Solo guardo documentos de texto ({allowed_list()}). "
        "Si es un libro o un PDF, mándalo como archivo, no como foto/vídeo/audio."
    )


async def save_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if message is None or user is None or message.document is None:
        return
    if not is_allowed(update):
        log.warning("Ignored file from unauthorized user %s", user.id)
        return

    doc = message.document
    name = safe_filename(doc.file_name or "documento")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        await message.reply_text(
            f"No guardo archivos «{suffix or 'sin extensión'}». Formatos admitidos: {allowed_list()}"
        )
        log.info("Rejected %s (extension not allowed)", name)
        return

    if not LOCAL_API_URL and doc.file_size and doc.file_size > CLOUD_API_MAX_BYTES:
        await message.reply_text(
            f"El archivo pesa {doc.file_size / 1024 / 1024:.1f} MB y la API pública de Telegram "
            "solo permite descargar hasta 20 MB. Configura TELEGRAM_LOCAL_API_URL para archivos grandes."
        )
        return

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = unique_path(DOWNLOAD_DIR, name)
    status = await message.reply_text(f"Descargando {target.name}…")
    try:
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(target)
    except Exception as exc:
        log.exception("Failed to download %s", target.name)
        target.unlink(missing_ok=True)
        await status.edit_text(f"Error al descargar {target.name}: {exc}")
        return

    log.info("Saved %s (%s bytes)", target, target.stat().st_size)
    await status.edit_text(f"Guardado: {target.name}")


def main() -> None:
    if not ALLOWED_USER_IDS:
        log.warning("TELEGRAM_ALLOWED_USER_IDS is empty: the bot will reject everyone. "
                    "Send /start to the bot to find out your id.")

    builder = (
        Application.builder()
        .token(BOT_TOKEN)
        # Big files take a while; the defaults (5 s) are too short.
        .read_timeout(300)
        .write_timeout(300)
        .media_write_timeout(300)
    )
    if LOCAL_API_URL:
        builder = (
            builder.base_url(f"{LOCAL_API_URL}/bot")
            .base_file_url(f"{LOCAL_API_URL}/file/bot")
            .local_mode(True)
        )
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, save_document))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE
        | filters.VIDEO_NOTE | filters.ANIMATION | filters.Sticker.ALL,
        reject_media,
    ))

    log.info("Bot running. Saving %s files to %s", allowed_list(), DOWNLOAD_DIR)
    # Process the messages that arrived while the bot was down (Telegram keeps them ~24 h).
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
