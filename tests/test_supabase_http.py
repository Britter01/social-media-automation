"""Tests for core.supabase_http.

Guards the workaround for Supabase dropping idle HTTP/2 connections, which
surfaced as httpx.RemoteProtocolError (ConnectionTerminated) on unrelated
calls — publishing, pause checks and the command queue.
"""

from __future__ import annotations

import httpx
import pytest

import core.supabase_http as sh


@pytest.fixture(autouse=True)
def _reset_install_flag(monkeypatch):
    """Let each test run install() from scratch without leaking state."""
    monkeypatch.setattr(sh, "_installed", False)
    yield


def _session_factories():
    from postgrest._sync.client import SyncPostgrestClient
    from storage3._sync.client import SyncStorageClient

    return (
        (SyncPostgrestClient, "create_session"),
        (SyncStorageClient, "_create_session"),
    )


def test_install_reports_success():
    assert sh.install() is True


def test_both_clients_build_http1_sessions_with_retries():
    sh.install()
    for klass, attr in _session_factories():
        session = getattr(klass, attr)(None, "https://example.supabase.co", {"apikey": "k"}, 30)
        assert isinstance(session, httpx.Client)
        # The whole point: HTTP/2 off, so no GOAWAY on a pooled connection.
        assert session._transport._pool._http2 is False
        assert session._transport._pool._retries == sh._CONNECT_RETRIES
        assert session.follow_redirects is True
        session.close()


def test_session_preserves_base_url_headers_and_timeout():
    # A patched factory that quietly dropped these would break every call.
    sh.install()
    klass, attr = _session_factories()[0]
    session = getattr(klass, attr)(
        None, "https://example.supabase.co", {"apikey": "secret-key"}, 42
    )
    assert str(session.base_url) == "https://example.supabase.co"
    assert session.headers["apikey"] == "secret-key"
    assert session.timeout.connect == 42
    session.close()


def _dummy_key() -> str:
    """A JWT-shaped key — create_client rejects anything else before connecting."""
    import base64
    import json

    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'HS256', 'typ': 'JWT'})}.{seg({'role': 'anon'})}.sig"


def test_real_create_client_gets_http1_sessions():
    """The behaviour that actually matters: clients built the normal way.

    Every call site in this codebase uses supabase.create_client directly, so
    patching the factories is only useful if it reaches that path.
    """
    from supabase import create_client

    sh.install()
    client = create_client("https://example.supabase.co", _dummy_key())

    for session in (client.postgrest.session, client.storage.session):
        assert session._transport._pool._http2 is False
        assert session._transport._pool._retries == sh._CONNECT_RETRIES
    # No network call is made here — create_client only builds the sessions.
    assert str(client.postgrest.session.base_url).startswith("https://example.supabase.co")


def test_install_is_idempotent():
    assert sh.install() is True
    assert sh.install() is True


def test_missing_attribute_degrades_instead_of_raising(monkeypatch):
    # If a future library version renames the factory, the app must still run —
    # just without the workaround — rather than failing to start.
    from storage3._sync.client import SyncStorageClient

    monkeypatch.delattr(SyncStorageClient, "_create_session", raising=True)
    assert sh.install() is False


def test_import_failure_degrades_instead_of_raising(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _boom(name, *args, **kwargs):
        if name.startswith(("postgrest", "storage3")):
            raise ImportError("simulated")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _boom)
    assert sh.install() is False
