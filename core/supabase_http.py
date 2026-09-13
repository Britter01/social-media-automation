"""Make the Supabase client's HTTP layer survive a flaky connection.

The worker talks to Supabase over long-lived pooled connections. ``postgrest``
and ``storage3`` both build their httpx session with ``http2=True`` hardcoded,
and Supabase's edge periodically sends an HTTP/2 GOAWAY on an idle connection.
httpx surfaces that as::

    httpx.RemoteProtocolError: <ConnectionTerminated error_code:0, ...>

on the *next* request to reuse that connection — so a perfectly healthy call
fails for reasons that have nothing to do with the request. In this codebase
that has caused, at least:

* a paused platform publishing anyway, because the pause-flag read threw and
  the check fell back to "not paused" (fixed separately in core.storage);
* "Failed to upsert post" on every post, every cycle, so the publish queue
  never drained;
* the command queue dying mid-claim and retrying for a minute before a
  dashboard button took effect.

Neither ``create_client`` nor ``ClientOptions`` exposes the http2 flag, so the
only place to turn it off is the session factory each sub-client uses. This
module patches those two factories to build an HTTP/1.1 session instead, with
connection-level retries. Call :func:`install` once, early, in any process that
talks to Supabase.

HTTP/1.1 costs nothing here: these are small, infrequent REST calls, and httpx
opens a fresh connection rather than reusing a half-dead pooled one.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Retries here cover connection establishment only (httpx does not replay a
# request that already reached the server). That is the right scope: it removes
# the reconnect race without risking a duplicate write.
_CONNECT_RETRIES = 3

_installed = False


def is_installed() -> bool:
    """Whether :func:`install` has successfully patched both clients.

    ``install`` runs at import, before logging is configured, so its own log
    line goes nowhere. Entry points use this to report the state once logging
    is up — otherwise there is no way to tell from the logs whether the
    workaround is actually active.
    """
    return _installed


def install() -> bool:
    """Force Supabase's HTTP sessions onto HTTP/1.1 with connection retries.

    Idempotent and best-effort: if a future version of ``postgrest`` or
    ``storage3`` restructures its session factory, this logs and returns False
    rather than stopping the process — the app still works, just with the
    original flaky HTTP/2 behaviour.

    Returns True if both clients were patched.
    """
    global _installed
    if _installed:
        return True

    try:
        import httpx
        from postgrest._sync.client import SyncPostgrestClient
        from storage3._sync.client import SyncStorageClient
    except Exception:
        logger.exception("Could not import Supabase HTTP clients — leaving HTTP/2 in place")
        return False

    def _session(_self, base_url, headers, timeout, verify=True, proxy=None):
        return httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            verify=bool(verify),
            proxy=proxy,
            follow_redirects=True,
            http2=False,
            transport=httpx.HTTPTransport(
                retries=_CONNECT_RETRIES, verify=bool(verify), proxy=proxy
            ),
        )

    # The two libraries spell the same factory differently: postgrest exposes
    # create_session, storage3 _create_session. Both are instance methods with
    # the same signature.
    targets = ((SyncPostgrestClient, "create_session"), (SyncStorageClient, "_create_session"))

    patched = 0
    for klass, attr in targets:
        if not hasattr(klass, attr):
            logger.warning(
                "Supabase HTTP: %s has no %s() — library layout changed, leaving it on HTTP/2",
                klass.__name__,
                attr,
            )
            continue
        try:
            setattr(klass, attr, _session)
            patched += 1
        except Exception:
            logger.exception("Could not patch %s.%s", klass.__name__, attr)

    _installed = patched == len(targets)
    if _installed:
        logger.info(
            "Supabase HTTP: HTTP/2 disabled, %d connection retries "
            "(works around GOAWAY on idle pooled connections)",
            _CONNECT_RETRIES,
        )
    else:
        logger.warning(
            "Supabase HTTP: only %d/%d clients patched — HTTP/2 may still be in use",
            patched,
            len(targets),
        )
    return _installed
