"""Tests for core.models."""

from __future__ import annotations

from datetime import UTC, datetime

from core.models import Post, PostStatus


def test_caption_with_hashtags_appends_and_prefixes_hash():
    post = Post(pillar="Review", platform="instagram", caption="Great earbuds.")
    post.hashtags = ["audio", "#tech"]
    out = post.caption_with_hashtags
    assert out.startswith("Great earbuds.")
    assert "#audio" in out
    assert "#tech" in out
    # No double-hashing.
    assert "##tech" not in out


def test_caption_with_hashtags_no_tags():
    post = Post(pillar="Review", platform="instagram", caption="Just text.")
    assert post.caption_with_hashtags == "Just text."


def test_mark_updates_status_and_timestamp():
    post = Post(pillar="AI Guide", platform="twitter")
    before = post.updated_at
    post.mark(PostStatus.PUBLISHED)
    assert post.status == PostStatus.PUBLISHED.value
    assert post.updated_at >= before
    assert post.error is None


def test_mark_records_error():
    post = Post(pillar="AI Guide", platform="twitter")
    post.mark(PostStatus.FAILED, error="boom")
    assert post.status == PostStatus.FAILED.value
    assert post.error == "boom"


def test_row_roundtrip_preserves_fields():
    post = Post(
        pillar="Productivity",
        platform="linkedin",
        topic="time blocking",
        caption="Block your calendar.",
        hashtags=["productivity", "focus"],
        title="Own your day",
    )
    post.scheduled_time = datetime(2026, 6, 2, 8, 0, tzinfo=UTC)

    row = post.to_row()
    restored = Post.from_row(row)

    assert restored.id == post.id
    assert restored.pillar == post.pillar
    assert restored.platform == post.platform
    assert restored.hashtags == post.hashtags
    assert restored.title == post.title
    assert restored.scheduled_time == post.scheduled_time


def test_from_row_tolerates_trailing_z():
    row = {
        "pillar": "Review",
        "platform": "youtube",
        "scheduled_time": "2026-06-02T08:00:00Z",
    }
    post = Post.from_row(row)
    assert post.scheduled_time is not None
    assert post.scheduled_time.year == 2026
