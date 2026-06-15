"""
backend/telegram_handlers.py

Full Telegram bot implementation. Runs in a background thread via main.py.
Handles 8 commands + inline button callbacks for Save/Reject.

Commands:
  /start    — generate 6-digit link code
  /jobs     — top 5 current matches
  /pause    — pause notifications
  /resume   — resume notifications
  /threshold [n] — update score threshold
  /health   — source health summary
  /status   — current settings
  /unlink   — unlink Telegram account
"""

import asyncio
import logging
import os
import random
import string
from datetime import datetime, timedelta, timezone

from supabase import create_client
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

logger = logging.getLogger("jobpulse.backend")

_STATUS_EMOJI = {
    "healthy": "🟢",
    "degraded": "🟡",
    "dead": "🔴",
    "low_quality": "⚠️",
}


def _get_supabase():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def _generate_code() -> str:
    """Generate a 6-digit numeric code."""
    return "".join(random.choices(string.digits, k=6))


# ── Commands ─────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate + store a 6-digit link code for account linking."""
    chat_id = update.effective_chat.id
    supabase = _get_supabase()

    # Check if already linked
    resp = (
        supabase.table("users")
        .select("id, email")
        .eq("telegram_chat_id", chat_id)
        .execute()
    )
    if resp.data:
        await update.message.reply_text(
            f"✅ Your Telegram is already linked to *{resp.data[0]['email']}*.\n\n"
            "Use /jobs to see your latest matches.",
            parse_mode="Markdown",
        )
        return

    code = _generate_code()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    supabase.table("telegram_link_codes").insert(
        {
            "telegram_chat_id": chat_id,
            "code": code,
            "expires_at": expires,
            "used": False,
        }
    ).execute()

    await update.message.reply_text(
        "👋 *Welcome to JobPulse!*\n\n"
        "To link your account, open the JobPulse web app → Profile → Telegram, "
        "and enter this code:\n\n"
        f"🔑 *{code}*\n\n"
        "_(Expires in 10 minutes)_",
        parse_mode="Markdown",
    )


async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show top 5 new matches for the linked user."""
    chat_id = update.effective_chat.id
    supabase = _get_supabase()

    user_resp = (
        supabase.table("users").select("id").eq("telegram_chat_id", chat_id).execute()
    )
    if not user_resp.data:
        await update.message.reply_text(
            "❌ Account not linked. Send /start to get your link code."
        )
        return

    user_id = user_resp.data[0]["id"]
    matches_resp = (
        supabase.table("job_matches")
        .select("*, jobs(*)")
        .eq("user_id", user_id)
        .in_("status", ["new", "seen"])
        .order("match_score", desc=True)
        .limit(5)
        .execute()
    )

    if not matches_resp.data:
        await update.message.reply_text(
            "No new matches right now. Check back after the next fetch! 🔍"
        )
        return

    await update.message.reply_text(
        f"🎯 *Your top {len(matches_resp.data)} matches:*", parse_mode="Markdown"
    )

    for m in matches_resp.data:
        job = m.get("jobs") or {}
        score = m["match_score"]
        text = (
            f"*{score}/100* — {job.get('title', 'Unknown')}\n"
            f"🏢 {job.get('company', 'Unknown')} | 🌍 Worldwide Remote\n"
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Apply 🔗", url=job.get("apply_url", "https://jobpulse.app")
                    ),
                    InlineKeyboardButton("Save ⭐", callback_data=f"save:{m['id']}"),
                ]
            ]
        )
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=keyboard
        )


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_frequency(update, "paused")


async def cmd_resume_notifs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_frequency(update, "realtime")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current user settings."""
    chat_id = update.effective_chat.id
    supabase = _get_supabase()

    resp = (
        supabase.table("users")
        .select("*, user_profiles(*)")
        .eq("telegram_chat_id", chat_id)
        .execute()
    )
    if not resp.data:
        await update.message.reply_text("Not linked. Send /start to get your link code.")
        return

    u = resp.data[0]
    profiles = u.get("user_profiles") or {}
    # Handle both list and dict from Supabase join
    if isinstance(profiles, list):
        profile = profiles[0] if profiles else {}
    else:
        profile = profiles

    seniority = ", ".join(profile.get("seniority_levels") or ["entry", "junior", "internship"])
    freq = u["notification_frequency"]
    freq_display = {"realtime": "Real-time 🔔", "daily": "Daily digest 📬", "paused": "Paused 🔕"}.get(freq, freq)

    await update.message.reply_text(
        f"⚙️ *Your JobPulse Settings*\n\n"
        f"📧 Account: `{u['email']}`\n"
        f"📊 Alert threshold: {u['notification_threshold']}/100\n"
        f"🔔 Notifications: {freq_display}\n"
        f"🎯 Min display score: {profile.get('min_display_score', 55)}\n"
        f"🎓 Seniority: {seniority}",
        parse_mode="Markdown",
    )


async def cmd_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Update the alert score threshold: /threshold 75"""
    chat_id = update.effective_chat.id
    supabase = _get_supabase()

    try:
        new_threshold = int(context.args[0])
        if not 0 <= new_threshold <= 100:
            raise ValueError
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Usage: /threshold 75\n(Must be a number between 0 and 100)"
        )
        return

    user_resp = (
        supabase.table("users").select("id").eq("telegram_chat_id", chat_id).execute()
    )
    if not user_resp.data:
        await update.message.reply_text("Not linked. Send /start")
        return

    supabase.table("users").update(
        {"notification_threshold": new_threshold}
    ).eq("id", user_resp.data[0]["id"]).execute()

    await update.message.reply_text(
        f"✅ Threshold updated to *{new_threshold}/100*\n"
        "You'll now receive alerts for jobs scoring at or above this threshold.",
        parse_mode="Markdown",
    )


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show health status of all active sources."""
    supabase = _get_supabase()
    sources = (
        supabase.table("job_sources")
        .select("name, health_status, last_job_count, is_active")
        .eq("is_active", True)
        .order("name")
        .execute()
    )

    if not sources.data:
        await update.message.reply_text("No active sources configured.")
        return

    lines = ["📡 *Source Health*\n"]
    for s in sources.data:
        emoji = _STATUS_EMOJI.get(s["health_status"], "❓")
        count = s.get("last_job_count") or 0
        lines.append(f"{emoji} {s['name']} — {count} jobs last run")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unlink Telegram from the user's account."""
    chat_id = update.effective_chat.id
    supabase = _get_supabase()
    supabase.table("users").update({"telegram_chat_id": None}).eq(
        "telegram_chat_id", chat_id
    ).execute()
    await update.message.reply_text(
        "✅ Your Telegram has been unlinked from JobPulse.\n"
        "Send /start to link again."
    )


# ── Inline button callbacks ───────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Save/Reject inline button presses from job alerts."""
    query = update.callback_query
    await query.answer()

    data: str = query.data
    chat_id = query.message.chat.id
    supabase = _get_supabase()

    # Resolve chat_id → user_id for ownership check (Security: prevents cross-user mutations)
    user_resp = (
        supabase.table("users").select("id").eq("telegram_chat_id", chat_id).execute()
    )
    if not user_resp.data:
        await query.message.reply_text("❌ Account not linked. Send /start to link.")
        return

    user_id = user_resp.data[0]["id"]

    if data.startswith("save:"):
        match_id = data.split(":", 1)[1]
        supabase.table("job_matches").update({"status": "saved"}).eq(
            "id", match_id
        ).eq("user_id", user_id).execute()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⭐ Saved! Find it in your Saved tab.")

    elif data.startswith("reject:"):
        match_id = data.split(":", 1)[1]
        supabase.table("job_matches").update({"status": "rejected"}).eq(
            "id", match_id
        ).eq("user_id", user_id).execute()
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("✖️ Dismissed.")


# ── Helpers ──────────────────────────────────────────────────────

async def _set_frequency(update: Update, frequency: str) -> None:
    chat_id = update.effective_chat.id
    supabase = _get_supabase()

    user_resp = (
        supabase.table("users").select("id").eq("telegram_chat_id", chat_id).execute()
    )
    if not user_resp.data:
        await update.message.reply_text("Not linked. Send /start to get your link code.")
        return

    supabase.table("users").update({"notification_frequency": frequency}).eq(
        "id", user_resp.data[0]["id"]
    ).execute()

    msg = {
        "paused": "🔕 Notifications paused. Send /resume to turn them back on.",
        "realtime": "🔔 Notifications resumed! You'll receive alerts for new high-match jobs.",
        "daily": "📬 Switched to daily digest mode.",
    }.get(frequency, "✅ Frequency updated.")

    await update.message.reply_text(msg)


# ── Bot runner ───────────────────────────────────────────────────

def run_bot(token: str) -> None:
    """
    Run the Telegram bot in polling mode.
    Called in a daemon thread from main.py on startup.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("jobs", cmd_jobs))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume_notifs))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("threshold", cmd_threshold))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("unlink", cmd_unlink))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info('{"event": "telegram_bot_polling_started"}')
    loop.run_until_complete(app.run_polling(drop_pending_updates=True))
