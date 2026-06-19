"""Runtime resolution and auto-refresh for the Meta (Facebook/Instagram) user token.

Meta long-lived user tokens last ~60 days. Rather than forcing a Railway
redeploy whenever the token is rotated, this module keeps a fresh token in the
Supabase ``app_settings`` table and exposes :func:`get_user_token`, which the
publisher and analytics agents call instead of reading the (static, possibly
stale) ``INSTAGRAM_ACCESS_TOKEN`` env var directly.

Resolution order in :func:`get_user_token`:
  1. A non-expired token stored in ``app_settings`` (the auto-refreshed one).
  2. ``config.instagram_access_token`` — the env var seed / manual fallback.

:func:`refresh_user_token` re-exchanges the current long-lived token for a new
one (resetting the ~60-day clock) using the app's ID + secret, and stores the
result. A weekly scheduler job calls it; see ``scheduler.cron.run_token_refresh``.

The ``app_settings`` table (create once in the Supabase SQL editor)::

    create table if not exists app_settings (
        key        text primary key,
        value      text,
        updated_at timestamptz not null default now()
    );

Everything degrades gracefully: if the table is missing, Supabase is
unreachable, or the app credentials aren't set, callers fall back to the env
var token so publishing is never blocked by this layer.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

import httpx

from core.config import Config, config

logger = logging.getLogger(__name__)

_GRAPH = "https://graph.facebook.com/v22.0"
_TABLE = "app_settings"
_KEY_TOKEN = "meta_user_token"
_KEY_EXPIRES = "meta_user_token_expires_at"

# Refresh once the stored token has fewer than this many days of life left.
_REFRESH_WHEN_DAYS_LEFT = 10

# In-process cache so the publish path doesn't hit Supabase on every call.
# The worker is a single long-lived process, so this persists across jobs;
# refresh_user_token() clears it directly when it rotates the token.
_CACHE_TTL = 300.0  # seconds
_cache: tuple[str | None, float] = (None, 0.0)


def _client(cfg: Config):
    """Return a Supabase client, or None if Supabase isn't configured."""
    if not (cfg.supabase_url and cfg.supabase_key):
        return None
    try:
        from supabase import create_client

        return create_client(cfg.supabase_url, cfg.supabase_key)
    except Exception:
        logger.debug("meta_token: could not build Supabase client", exc_info=True)
        return None


def _get_setting(sb, key: str) -> str | None:
    try:
        rows = sb.table(_TABLE).select("value").eq("key", key).limit(1).execute().data or []
        return rows[0]["value"] if rows else None
    except Exception:
        # Table missing / unreadable — silently fall back to the env var.
        logger.debug("meta_token: could not read %s", key, exc_info=True)
        return None


def _set_setting(sb, key: str, value: str) -> None:
    sb.table(_TABLE).upsert(
        {"key": key, "value": value, "updated_at": datetime.now(UTC).isoformat()}
    ).execute()


def _stored_token(sb) -> str | None:
    """Return the stored token if present and not expired, else None."""
    token = _get_setting(sb, _KEY_TOKEN)
    if not token:
        return None
    expires_raw = _get_setting(sb, _KEY_EXPIRES)
    if expires_raw:
        try:
            expires_at = datetime.fromisoformat(expires_raw)
            if expires_at <= datetime.now(UTC):
                logger.warning("meta_token: stored token expired at %s", expires_raw)
                return None
        except ValueError:
            pass
    return token


def get_user_token(cfg: Config = config) -> str | None:
    """Return the Meta user token to use for API calls.

    Prefers a fresh token stored in ``app_settings``; falls back to the
    ``INSTAGRAM_ACCESS_TOKEN`` env var. Cached in-process for a few minutes.
    """
    global _cache
    cached, fetched_at = _cache
    if cached and (time.monotonic() - fetched_at) < _CACHE_TTL:
        return cached

    token = cfg.instagram_access_token  # default / fallback
    sb = _client(cfg)
    if sb is not None:
        stored = _stored_token(sb)
        if stored:
            token = stored

    _cache = (token, time.monotonic())
    return token


def clear_cache() -> None:
    """Drop the in-process token cache (called after a refresh)."""
    global _cache
    _cache = (None, 0.0)


def token_info(cfg: Config = config) -> dict:
    """Return a small status dict for diagnostics (no token value exposed)."""
    sb = _client(cfg)
    info: dict = {"source": "env", "expires_at": None, "days_left": None}
    if sb is None:
        return info
    stored = _get_setting(sb, _KEY_TOKEN)
    if stored:
        info["source"] = "app_settings"
    expires_raw = _get_setting(sb, _KEY_EXPIRES)
    if expires_raw:
        info["expires_at"] = expires_raw
        try:
            delta = datetime.fromisoformat(expires_raw) - datetime.now(UTC)
            info["days_left"] = max(0, delta.days)
        except ValueError:
            pass
    return info


def refresh_user_token(cfg: Config = config, *, force: bool = False) -> tuple[bool, str]:
    """Re-exchange the current long-lived token for a fresh ~60-day one.

    Returns ``(changed, message)``. ``changed`` is True only when a new token
    was fetched and stored. Skips the network call when the stored token still
    has plenty of life left (unless ``force=True``).
    """
    if not (cfg.facebook_app_id and cfg.facebook_app_secret):
        return False, "FACEBOOK_APP_ID / FACEBOOK_APP_SECRET not set — cannot auto-refresh"

    sb = _client(cfg)
    if sb is None:
        return False, "Supabase not configured — nowhere to store the refreshed token"

    # Skip if we still have comfortable headroom.
    if not force:
        expires_raw = _get_setting(sb, _KEY_EXPIRES)
        if expires_raw:
            try:
                days_left = (datetime.fromisoformat(expires_raw) - datetime.now(UTC)).days
                if days_left > _REFRESH_WHEN_DAYS_LEFT:
                    return False, f"token still valid for {days_left}d — no refresh needed"
            except ValueError:
                pass

    current = _stored_token(sb) or cfg.instagram_access_token
    if not current:
        return False, "no current token available to exchange"

    try:
        resp = httpx.get(
            f"{_GRAPH}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": cfg.facebook_app_id,
                "client_secret": cfg.facebook_app_secret,
                "fb_exchange_token": current,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return False, f"exchange request failed: {type(exc).__name__}: {str(exc)[:200]}"

    new_token = data.get("access_token")
    if not new_token:
        return False, f"no access_token in response: {str(data)[:200]}"

    expires_in = int(data.get("expires_in") or 0)
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in or 60 * 24 * 3600)

    try:
        _set_setting(sb, _KEY_TOKEN, new_token)
        _set_setting(sb, _KEY_EXPIRES, expires_at.isoformat())
    except Exception as exc:
        return (
            False,
            f"could not store refreshed token (does app_settings exist?): {str(exc)[:150]}",
        )

    clear_cache()
    return True, f"refreshed — new token valid until {expires_at.date().isoformat()}"
