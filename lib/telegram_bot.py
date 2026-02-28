"""Telegram bot for a2pod — accepts URLs, runs pipeline, delivers audio."""

import asyncio
import configparser
import logging
import re
from functools import partial
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from errors import PipelineError
from pipeline import run_pipeline

_CONFIG_PATH = Path.home() / ".config" / "a2pod" / "config"

logger = logging.getLogger(__name__)


def load_telegram_config() -> tuple[str, set[int]]:
    """Read [telegram] section from config. Returns (bot_token, allowed_user_ids)."""
    cfg = configparser.RawConfigParser()
    cfg.read(_CONFIG_PATH)

    token = cfg.get("telegram", "bot_token", fallback="").strip()
    if not token:
        raise SystemExit(
            f"Telegram bot token not configured.\n"
            f"Add it to {_CONFIG_PATH}:\n\n"
            f"[telegram]\nbot_token = YOUR_BOT_TOKEN\n"
            f"allowed_users = YOUR_USER_ID"
        )

    raw_users = cfg.get("telegram", "allowed_users", fallback="").strip()
    if not raw_users:
        raise SystemExit(
            f"No allowed users configured.\n"
            f"Add allowed_users to [telegram] section in {_CONFIG_PATH}:\n\n"
            f"allowed_users = 123456789,987654321"
        )

    allowed = set()
    for uid in raw_users.split(","):
        uid = uid.strip()
        if uid.isdigit():
            allowed.add(int(uid))

    if not allowed:
        raise SystemExit("No valid user IDs in allowed_users config.")

    return token, allowed


def _is_authorized(user_id: int, allowed: set[int]) -> bool:
    return user_id in allowed


async def _reject_unauthorized(update: Update) -> None:
    await update.message.reply_text("Sorry, you are not authorized to use this bot.")


async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed = context.bot_data["allowed_users"]
    if not _is_authorized(update.effective_user.id, allowed):
        return await _reject_unauthorized(update)
    await update.message.reply_text(
        "Welcome to A2Pod!\n\n"
        "Send me an article URL and I'll convert it to audio.\n"
        "Use /help for more info."
    )


async def _help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed = context.bot_data["allowed_users"]
    if not _is_authorized(update.effective_user.id, allowed):
        return await _reject_unauthorized(update)
    await update.message.reply_text(
        "Send me any article URL and I'll:\n"
        "1. Extract the text\n"
        "2. Clean it for audio\n"
        "3. Generate speech with Kokoro TTS\n"
        "4. Send you the audio file\n\n"
        "Supported: regular web articles, X/Twitter posts and articles."
    )


def _run_pipeline_sync(url: str, loop: asyncio.AbstractEventLoop, chat_id: int,
                        status_message_id: int, bot, progress_lines: list[str]) -> dict:
    """Run the sync pipeline in a thread, bridging progress back to async."""

    def on_progress(msg: str) -> None:
        progress_lines.append(msg)
        text = "\n".join(progress_lines)
        # Fire-and-forget edit of the status message
        asyncio.run_coroutine_threadsafe(
            bot.edit_message_text(chat_id=chat_id, message_id=status_message_id, text=text),
            loop,
        )

    return run_pipeline(url=url, no_upload=False, on_progress=on_progress)


async def _handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    allowed = context.bot_data["allowed_users"]
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    if not _is_authorized(user_id, allowed):
        logger.warning("Unauthorized access from @%s (id=%d)", username, user_id)
        return await _reject_unauthorized(update)

    # Per-user serialization: prevent concurrent jobs
    active_jobs: set = context.bot_data.setdefault("active_jobs", set())
    if user_id in active_jobs:
        await update.message.reply_text("You already have a job in progress. Please wait for it to finish.")
        return

    text = update.message.text.strip()

    # Extract URL from message
    url_match = re.search(r"https?://\S+", text)
    if not url_match:
        await update.message.reply_text("Please send a valid URL starting with http:// or https://")
        return

    url = url_match.group(0)
    active_jobs.add(user_id)
    logger.info("Job started for @%s: %s", username, url)

    # Send initial status message
    progress_lines = ["Starting pipeline..."]
    status_msg = await update.message.reply_text(progress_lines[0])

    loop = asyncio.get_running_loop()

    try:
        result = await loop.run_in_executor(
            None,
            partial(
                _run_pipeline_sync,
                url=url,
                loop=loop,
                chat_id=update.effective_chat.id,
                status_message_id=status_msg.message_id,
                bot=context.bot,
                progress_lines=progress_lines,
            ),
        )

        title = result["title"]
        size_mb = result["size_mb"]
        summary = result.get("summary") or ""

        msg = f"*{title}*"
        if summary:
            msg += f"\n\n{summary}"
        msg += f"\n\n_{size_mb:.1f} MB_"
        if result.get("feed_url"):
            msg += f" · [Podcast feed]({result['feed_url']})"

        await update.message.reply_text(msg, parse_mode="Markdown")
        logger.info("Job done for @%s: %s (%.1f MB)", username, title, size_mb)

    except PipelineError as e:
        logger.error("Pipeline error for @%s on %s: %s", username, url, e)
        await update.message.reply_text(f"Error: {e}")
    except Exception:
        logger.exception("Unexpected error for @%s on %s", username, url)
        await update.message.reply_text("An unexpected error occurred. Check the bot logs for details.")
    finally:
        active_jobs.discard(user_id)


def run_bot() -> None:
    """Start the Telegram bot with long-polling."""
    token, allowed = load_telegram_config()

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    # Silence noisy HTTP request logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    app = Application.builder().token(token).build()
    app.bot_data["allowed_users"] = allowed

    app.add_handler(CommandHandler("start", _start))
    app.add_handler(CommandHandler("help", _help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_url))

    logger.info("Bot started (allowed users: %s)", allowed)
    app.run_polling()
