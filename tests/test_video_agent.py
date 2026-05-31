"""Tests for agents.video_agent helpers and submission flow."""

from __future__ import annotations

from agents.video_agent import _dimension_for, _script_from_post
from core.models import Post


def test_dimension_is_vertical_for_short_form():
    assert _dimension_for("tiktok") == {"width": 1080, "height": 1920}
    assert _dimension_for("instagram") == {"width": 1080, "height": 1920}


def test_dimension_is_landscape_for_youtube():
    assert _dimension_for("youtube") == {"width": 1920, "height": 1080}


def test_script_leads_with_title_and_caps_length():
    post = Post(
        pillar="Review",
        platform="youtube",
        title="Top earbuds 2026",
        caption="x" * 5000,
    )
    script = _script_from_post(post)
    assert script.startswith("Top earbuds 2026.")
    assert len(script) <= 1500


def test_script_falls_back_to_caption_without_title():
    post = Post(pillar="Review", platform="tiktok", caption="Just the caption.")
    assert _script_from_post(post) == "Just the caption."
