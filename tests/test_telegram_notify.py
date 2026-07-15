"""Tests for core.telegram_notify caption handling."""

from __future__ import annotations

import dataclasses

import core.telegram_notify as tn


class _FakePost:
    def __init__(self, caption, post_type="carousel", slides=None, thumbnail_url=""):
        self.id = "test-post"
        self.caption = caption
        self.hashtags = []
        self.post_type = post_type
        self.slides = slides or []
        self.thumbnail_url = thumbnail_url
        self.video_url = ""

    @property
    def caption_with_hashtags(self):
        return self.caption


def _cfg(base_config):
    return dataclasses.replace(base_config, telegram_bot_token="tok", telegram_chat_id="chat")


def _capture(monkeypatch):
    calls = []
    monkeypatch.setattr(tn, "_tg", lambda token, method, payload: calls.append((method, payload)))
    return calls


def test_short_caption_stays_inline_on_the_image(base_config, monkeypatch):
    calls = _capture(monkeypatch)
    post = _FakePost(
        "Short and sweet caption.",
        slides=[{"image_url": "http://x/1.png"}, {"image_url": "http://x/2.png"}],
    )
    assert tn.send_post_to_telegram(post, "instagram", _cfg(base_config)) is True
    methods = [m for m, _ in calls]
    assert methods == ["sendMediaGroup"]  # no separate caption message needed
    first_caption = calls[0][1]["media"][0]["caption"]
    assert "Short and sweet caption." in first_caption


def test_long_caption_is_sent_as_separate_messages_not_truncated(base_config, monkeypatch):
    calls = _capture(monkeypatch)
    long_caption = "\n\n".join(f"{i}. Story headline\n" + "detail " * 60 for i in range(1, 4))
    assert len(long_caption) > tn._TG_MEDIA_CAPTION_MAX  # over the media-caption cap
    post = _FakePost(
        long_caption,
        slides=[{"image_url": "http://x/1.png"}, {"image_url": "http://x/2.png"}],
    )
    assert tn.send_post_to_telegram(post, "instagram", _cfg(base_config)) is True

    methods = [m for m, _ in calls]
    assert methods[0] == "sendMediaGroup"
    # The image caption carries only the header pointer, never the truncated body.
    img_caption = calls[0][1]["media"][0]["caption"]
    assert len(img_caption) <= tn._TG_MEDIA_CAPTION_MAX
    assert "Full caption below" in img_caption

    # The full caption is delivered via one or more sendMessage calls…
    sent = "\n\n".join(p["text"] for m, p in calls if m == "sendMessage")
    assert all(len(p["text"]) <= tn._TG_TEXT_MAX for m, p in calls if m == "sendMessage")
    # …and every story's detail survives (nothing cut off).
    for i in (1, 2, 3):
        assert f"{i}. Story headline" in sent


def test_missing_credentials_returns_false(base_config, monkeypatch):
    _capture(monkeypatch)
    post = _FakePost("hi", slides=[{"image_url": "http://x/1.png"}])
    # base_config has no telegram creds
    assert tn.send_post_to_telegram(post, "instagram", base_config) is False
