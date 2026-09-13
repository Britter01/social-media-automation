"""Tests for the Higgsfield Soul image provider.

These pin the request to Higgsfield's published OpenAPI contract. The previous
code posted to a stale host with two fields that no longer exist, which the API
rejected with a bare 422 — and because requests' raise_for_status() discards the
body, the logs never said why.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from agents.thumbnail_agent import _HIGGSFIELD_BASE, ThumbnailAgent
from core.models import Post


class _Resp:
    def __init__(self, status_code=200, payload=None, content=b"", url="https://x/y", text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.url = url
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


@pytest.fixture
def agent(base_config):
    cfg = dataclasses.replace(base_config, higgsfield_api_key="id:secret")
    return ThumbnailAgent(cfg)


def _patch_requests(monkeypatch, post_resp, get_responses):
    """Wire fake requests.post/get and record what was sent."""
    sent = {}
    gets = list(get_responses)

    def _post(url, headers=None, json=None, timeout=None):
        sent["url"] = url
        sent["headers"] = headers or {}
        sent["body"] = json or {}
        return post_resp

    def _get(url, headers=None, timeout=None):
        sent.setdefault("get_urls", []).append(url)
        return gets.pop(0)

    monkeypatch.setattr("requests.post", _post)
    monkeypatch.setattr("requests.get", _get)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    return sent


def test_request_matches_the_published_schema(monkeypatch, agent):
    submit = _Resp(payload={"request_id": "req-1", "status_url": "https://api.x/status"})
    status = _Resp(payload={"status": "completed", "images": [{"url": "https://img/1.png"}]})
    sent = _patch_requests(monkeypatch, submit, [status, _Resp(content=b"IMGBYTES")])

    out = agent._generate_higgsfield(Post(pillar="AI Guide", platform="linkedin"), "a prompt")

    assert out == b"IMGBYTES"
    assert sent["url"] == f"{_HIGGSFIELD_BASE}/higgsfield-ai/soul/standard"
    assert sent["headers"]["Authorization"] == "Key id:secret"
    # Exactly the documented fields — an unknown key is what caused the 422.
    assert set(sent["body"]) == {"prompt", "aspect_ratio", "num_images"}
    assert sent["body"]["aspect_ratio"] == "1:1"
    assert sent["body"]["num_images"] == 1


def test_polls_the_status_url_the_api_returns(monkeypatch, agent):
    submit = _Resp(payload={"request_id": "req-2", "status_url": "https://api.x/custom-status"})
    status = _Resp(payload={"status": "completed", "images": [{"url": "https://img/2.png"}]})
    sent = _patch_requests(monkeypatch, submit, [status, _Resp(content=b"OK")])

    agent._generate_higgsfield(Post(pillar="AI Guide", platform="linkedin"), "p")

    assert sent["get_urls"][0] == "https://api.x/custom-status"


def test_falls_back_to_constructed_status_url(monkeypatch, agent):
    submit = _Resp(payload={"request_id": "req-3"})  # no status_url
    status = _Resp(payload={"status": "completed", "images": [{"url": "https://img/3.png"}]})
    sent = _patch_requests(monkeypatch, submit, [status, _Resp(content=b"OK")])

    agent._generate_higgsfield(Post(pillar="AI Guide", platform="linkedin"), "p")

    assert sent["get_urls"][0] == f"{_HIGGSFIELD_BASE}/requests/req-3/status"


def test_http_error_surfaces_the_response_body(monkeypatch, agent):
    submit = _Resp(
        status_code=422,
        url="https://api.higgsfield.ai/higgsfield-ai/soul/standard",
        text='{"detail":[{"loc":["body","quality"],"msg":"extra fields not permitted"}]}',
    )
    _patch_requests(monkeypatch, submit, [])

    with pytest.raises(RuntimeError) as exc:
        agent._generate_higgsfield(Post(pillar="AI Guide", platform="linkedin"), "p")

    # The body is the whole point — a bare "422 Unprocessable Entity" is useless.
    assert "422" in str(exc.value)
    assert "extra fields not permitted" in str(exc.value)


@pytest.mark.parametrize("status", ["failed", "nsfw", "canceled"])
def test_terminal_failures_raise_immediately(monkeypatch, agent, status):
    # Each must break the poll loop; otherwise a dead job burns the full
    # 5-minute timeout before anyone hears about it.
    submit = _Resp(payload={"request_id": "req-4"})
    _patch_requests(monkeypatch, submit, [_Resp(payload={"status": status, "error": "nope"})])

    with pytest.raises(RuntimeError, match=status):
        agent._generate_higgsfield(Post(pillar="AI Guide", platform="linkedin"), "p")


def test_keeps_polling_through_non_terminal_states(monkeypatch, agent):
    submit = _Resp(payload={"request_id": "req-5"})
    responses = [
        _Resp(payload={"status": "queued"}),
        _Resp(payload={"status": "in_progress"}),
        _Resp(payload={"status": "completed", "images": [{"url": "https://img/5.png"}]}),
        _Resp(content=b"FINAL"),
    ]
    _patch_requests(monkeypatch, submit, responses)

    assert agent._generate_higgsfield(Post(pillar="AI Guide", platform="linkedin"), "p") == b"FINAL"


def test_aspect_ratios_are_all_valid_for_the_api():
    """Every mapped ratio must be in Higgsfield's documented enum."""
    from agents.thumbnail_agent import _ASPECT_RATIO

    allowed = {"1:1", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "16:9", "9:16", "21:9"}
    assert set(_ASPECT_RATIO.values()) <= allowed


def test_image_url_may_be_a_bare_string(monkeypatch, agent):
    submit = _Resp(payload={"request_id": "req-6"})
    status = _Resp(payload={"status": "completed", "images": ["https://img/6.png"]})
    _patch_requests(monkeypatch, submit, [status, _Resp(content=b"BARE")])

    assert agent._generate_higgsfield(Post(pillar="AI Guide", platform="linkedin"), "p") == b"BARE"


def test_generate_raw_falls_back_to_imagen_when_higgsfield_fails(monkeypatch, agent):
    """The fallback is what kept posts working; it must survive this change."""
    monkeypatch.setattr(
        ThumbnailAgent,
        "_generate_higgsfield",
        lambda self, post, prompt: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(ThumbnailAgent, "_visual_scene", lambda self, post: "scene")
    agent._imagen_client = SimpleNamespace(
        models=SimpleNamespace(
            generate_images=lambda **kw: SimpleNamespace(
                generated_images=[SimpleNamespace(image=SimpleNamespace(image_bytes=b"IMAGEN"))]
            )
        )
    )

    assert agent.generate_raw(Post(pillar="AI Guide", platform="linkedin")) == b"IMAGEN"
