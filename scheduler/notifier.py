"""
scheduler/notifier.py

Sends Telegram job alerts with inline buttons (Apply / Save / Reject).
Called at the end of each scheduler run with accumulated alerts.
"""

import asyncio
import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger("jobpulse.scheduler")

_SCORE_EMOJI = {
    90: "🔥",  # ≥90
    75: "🎯",  # ≥75
    60: "✅",  # ≥60
    0:  "📋",  # <60
}

_CURRENCY_EMOJI = {
    "usd": "💵",
    "gbp": "💷",
    "eur": "💶",
}

_SENIORITY_BADGE = {
    "internship": "[🎓 Internship]",
    "entry": "[🟢 Entry-level]",
    "junior": "[🔵 Junior]",
}


def _score_emoji(score: int) -> str:
    for threshold in sorted(_SCORE_EMOJI.keys(), reverse=True):
        if score >= threshold:
            return _SCORE_EMOJI[threshold]
    return "📋"


async def _send_job_alert(bot: Bot, chat_id: int, job: dict, match: dict) -> None:
    score: int = match.get("match_score", 0)
    reasons = match.get("match_reasons") or []
    currency = match.get("currency_signal", "")

    score_em = _score_emoji(score)
    curr_em = _CURRENCY_EMOJI.get(currency, "❓")

    seniority_badge = ""
    if job.get("is_trainee"):
        seniority_badge = "[📚 Trainee Program]"
    else:
        seniority_badge = _SENIORITY_BADGE.get(job.get("seniority", ""), "")

    reasons_text = (
        "  ".join([f"✅ {r}" for r in reasons[:3]]) if reasons else ""
    )

    text = (
        f"{score_em} *New Match — {score}/100*\n\n"
        f"💼 {job.get('title', 'Unknown Role')} {seniority_badge}\n"
        f"🏢 {job.get('company', 'Unknown Company')}\n"
        f"🌍 Worldwide Remote | {curr_em}\n"
        f"📅 Via: {job.get('source_name', 'Job Board')}\n"
    )

    if reasons_text:
        text += f"\n{reasons_text}"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Apply Now 🔗",
                    url=job.get("apply_url", "https://jobpulse.app"),
                ),
                InlineKeyboardButton(
                    "Save ⭐",
                    callback_data=f"save:{match['id']}",
                ),
                InlineKeyboardButton(
                    "Not for me ✖️",
                    callback_data=f"reject:{match['id']}",
                ),
            ]
        ]
    )

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


def send_alerts(alerts: list, bot_token: str) -> None:
    """
    Send all accumulated Telegram alerts.

    alerts: list of (chat_id, job_dict, match_dict) tuples
    """
    if not alerts:
        return

    bot = Bot(token=bot_token)

    async def _run():
        for chat_id, job, match in alerts:
            try:
                await _send_job_alert(bot, chat_id, job, match)
            except Exception as e:
                logger.error(
                    '{"event": "telegram_alert_error", "chat_id": %d, "error": "%s"}',
                    chat_id,
                    str(e),
                )

    asyncio.run(_run())
