"""Tests for the per-platform image on/off switch.

Turning images off must actually skip the Imagen call — the point is to save
the spend and the failure noise, not just to drop the picture afterwards.
"""

from __future__ import annotations

import pytest

import scheduler.cron as cron
from core.models import Post


class _RecordingThumbnailAgent:
    """Fails loudly if the pipeline calls it when images are off."""

    def __init__(self):
        self.calls = 0

    def generate_raw(self, post):
        self.calls += 1
        return b"fake-image-bytes"

    def apply_overlay(self, raw):
        return raw

    def upload(self, post, data):
        post.thumbnail_url = "https://example.test/img.png"


def _linkedin_post():
    return Post(pillar="AI Guide", platform="linkedin", caption="Hello")


def test_images_off_skips_generation_entirely(monkeypatch):
    monkeypatch.setattr(cron, "_are_platform_images_disabled", lambda platform: True)
    agent = _RecordingThumbnailAgent()
    post = _linkedin_post()

    cron._generate_media(post, agent, video_agent=None)

    assert agent.calls == 0, "Imagen must not be called when images are off"
    assert post.thumbnail_url is None
    assert not post.error, "a deliberate setting is not an error"


def test_images_on_still_generates(monkeypatch):
    monkeypatch.setattr(cron, "_are_platform_images_disabled", lambda platform: False)
    agent = _RecordingThumbnailAgent()
    post = _linkedin_post()

    cron._generate_media(post, agent, video_agent=None)

    assert agent.calls == 1
    assert post.thumbnail_url == "https://example.test/img.png"


def test_only_the_named_platform_is_affected(monkeypatch):
    monkeypatch.setattr(
        cron, "_are_platform_images_disabled", lambda platform: platform == "linkedin"
    )
    twitter_agent = _RecordingThumbnailAgent()
    twitter_post = Post(pillar="AI Guide", platform="twitter", caption="Hi")

    cron._generate_media(twitter_post, twitter_agent, video_agent=None)

    assert twitter_agent.calls == 1, "turning LinkedIn off must not touch X"


def test_carousel_platforms_are_refused(monkeypatch):
    # IG/FB slides ARE the post — accepting the setting would silently do
    # nothing, so it is rejected instead.
    for platform in ("instagram", "facebook"):
        with pytest.raises(RuntimeError, match="carousel-only"):
            cron.run_set_platform_images(platform, enabled=False)


def test_flag_read_fails_open_to_images_on(monkeypatch):
    """An unreadable flag must not silently strip images.

    Unlike a publishing pause, guessing wrong here is cosmetic and the next run
    corrects it — so this fails open rather than closed.
    """
    import core.storage as storage_mod

    def _boom(*a, **k):
        raise ConnectionError("storage down")

    monkeypatch.setattr(
        storage_mod, "get_storage", lambda *a, **k: type("S", (), {"download": _boom})()
    )
    monkeypatch.setattr("time.sleep", lambda _s: None)

    assert cron._are_platform_images_disabled("linkedin") is False
