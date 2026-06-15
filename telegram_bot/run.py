"""
telegram_bot/run.py

Standalone Telegram bot entry point.
Used by .github/workflows/telegram-bot.yml (Option B — pure $0).

Imports the bot handlers from the backend module.
GitHub Actions job timeout is 6 hours — python-telegram-bot handles
SIGTERM gracefully, so the cron restart causes a clean reconnect.

Usage:
    python telegram_bot/run.py

Environment variables required:
    TELEGRAM_BOT_TOKEN
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
"""

import os
import sys
import logging
import signal
import threading

# Add backend/ to path so we can import telegram_handlers
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Load .env for local dev (no-op in GitHub Actions where env vars are injected)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
except ImportError:
    pass

logging.basicConfig(
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "msg": "%(message)s"}',
    level=logging.INFO,
)
logger = logging.getLogger("jobpulse.bot")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error('{"event": "bot_startup_failed", "reason": "TELEGRAM_BOT_TOKEN not set"}')
        sys.exit(1)

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        logger.error('{"event": "bot_startup_failed", "reason": "Supabase env vars not set"}')
        sys.exit(1)

    logger.info('{"event": "bot_starting", "mode": "standalone_github_actions"}')

    # Schedule a clean SIGINT right before the 350-minute GitHub Actions timeout
    # This ensures the process exits cleanly (Code 0) and the GitHub job shows as Green ✅
    def clean_exit():
        logger.info('{"event": "bot_timeout_reached", "msg": "349 minutes elapsed. Shutting down cleanly."}')
        os.kill(os.getpid(), signal.SIGINT)

    timer = threading.Timer(349 * 60, clean_exit)
    timer.daemon = True
    timer.start()

    try:
        from telegram_handlers import run_bot
        run_bot(token)  # Blocks until SIGTERM/SIGINT
    except KeyboardInterrupt:
        logger.info('{"event": "bot_stopped", "reason": "KeyboardInterrupt"}')
    except Exception as e:
        logger.error(f'{{"event": "bot_crashed", "error": "{str(e)}"}}')
        sys.exit(1)


if __name__ == "__main__":
    main()
