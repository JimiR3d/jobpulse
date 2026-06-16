"""
backend/main.py

JobPulse FastAPI application.
Applies all security patches from the Security Patch document:
  - CORS locked to FRONTEND_URL in production (Patch #2)
  - 5MB request size limit (Patch #3)
  - Rate limiting via slowapi (Patch #3)
  - Global exception handler — no stack traces to client (Patch #4)
  - Structured JSON logging (Patch #4)
  - Telegram bot starts in background thread on startup
"""

import json
import logging
import os
import threading
import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

# ── Structured logging ───────────────────────────────────────────
logging.basicConfig(
    format='{"time": "%(asctime)s", "level": "%(levelname)s", "message": %(message)s}',
    level=logging.INFO,
)
logger = logging.getLogger("jobpulse.backend")

# ── App + Rate limiter ───────────────────────────────────────────
app = FastAPI(
    title="JobPulse API",
    description="Personal AI-powered remote job aggregator",
    version="1.0.0",
    # Disable default docs in production to reduce attack surface
    docs_url="/docs" if os.environ.get("ENV") != "production" else None,
    redoc_url=None,
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS — Security Patch #2 ─────────────────────────────────────
# Locked to the Vercel frontend URL in production.
# Localhost allowed only in development.
ALLOWED_ORIGINS = (
    [os.environ["FRONTEND_URL"]]
    if os.environ.get("ENV") == "production"
    else ["http://localhost:5173", "http://localhost:3000", "http://localhost:4173"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Api-Key", "Cache-Control", "Pragma"],
    max_age=86400,
)

# ── Request size limit — Security Patch #3 ───────────────────────
@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 5_000_000:  # 5MB max
        return JSONResponse(
            status_code=413,
            content={"error": "Request payload too large (5MB maximum)"},
        )
    return await call_next(request)

# ── Global exception handlers — Security Patch #4 ────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Log full details server-side. Return generic message to client — never expose internals."""
    logger.error(
        json.dumps({
            "event": "unhandled_exception",
            "path": str(request.url),
            "method": request.method,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error. Please try again later."},
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(
        json.dumps({
            "event": "http_exception",
            "path": str(request.url),
            "status_code": exc.status_code,
            "detail": exc.detail,
        })
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
    )

# ── Routes ───────────────────────────────────────────────────────
from routes import jobs, sources, profile, imports, telegram_routes, applications  # noqa: E402

app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])
app.include_router(imports.router, prefix="/api/imports", tags=["imports"])
app.include_router(telegram_routes.router, prefix="/api/telegram", tags=["telegram"])
app.include_router(applications.router, prefix="/api/applications", tags=["applications"])

# ── Health check ─────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "service": "JobPulse API", "version": "1.0.0"}

# ── Telegram bot in background thread ───────────────────────────
def _start_telegram_bot():
    """Runs in a daemon thread so it doesn't block FastAPI startup."""
    import telegram_handlers  # noqa: F401 — imported here to avoid circular import
    telegram_handlers.run_bot(os.environ["TELEGRAM_BOT_TOKEN"])

@app.on_event("startup")
async def startup_event():
    logger.info(json.dumps({"event": "startup", "env": os.environ.get("ENV", "development")}))
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    # START_TELEGRAM_BOT=false when deploying on Render free tier (bot runs in GitHub Actions)
    # START_TELEGRAM_BOT=true  when deploying on Render Starter or Fly.io (bot embedded)
    start_bot = os.environ.get("START_TELEGRAM_BOT", "true").lower() == "true"
    if bot_token and start_bot:
        thread = threading.Thread(target=_start_telegram_bot, daemon=True)
        thread.start()
        logger.info(json.dumps({"event": "telegram_bot_started", "mode": "embedded"}))
    elif bot_token and not start_bot:
        logger.info(json.dumps({"event": "telegram_bot_skipped", "reason": "START_TELEGRAM_BOT=false — bot runs externally"}))
    else:
        logger.warning(json.dumps({"event": "telegram_bot_skipped", "reason": "TELEGRAM_BOT_TOKEN not set"}))
