"""Tests for agents.content_agent (Anthropic client mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents.content_agent import ContentAgent, GeneratedContent
from core.models import Post, PostStatus


def _fake_response(title, caption, hashtags, stop_reason="end_turn"):
    return SimpleNamespace(
        parsed_output=GeneratedContent(title=title, caption=caption, hashtags=hashtags),
        stop_reason=stop_reason,
        usage=SimpleNamespace(cache_read_input_tokens=10, input_tokens=100, output_tokens=50),
    )


def test_generate_populates_post_and_strips_hashes(base_config):
    agent = ContentAgent(base_config)
    agent._client = MagicMock()
    agent._client.messages.parse.return_value = _fake_response(
        "Hook", "A clear caption.", ["#tech", "audio"]
    )

    post = Post(pillar="Review", platform="instagram", topic="earbuds")
    agent.generate(post)

    assert post.title == "Hook"
    assert post.caption == "A clear caption."
    assert post.hashtags == ["tech", "audio"]  # leading '#' stripped
    assert post.status == PostStatus.CONTENT_READY.value


def test_generate_uses_correct_model_and_caching(base_config):
    agent = ContentAgent(base_config)
    agent._client = MagicMock()
    agent._client.messages.parse.return_value = _fake_response("T", "C", ["x"])

    post = Post(pillar="AI Guide", platform="linkedin")
    agent.generate(post)

    _, kwargs = agent._client.messages.parse.call_args
    # Caption writing uses the creative tier (Sonnet), never Opus.
    assert kwargs["model"] == base_config.model_creative
    assert "opus" not in kwargs["model"]
    assert kwargs["thinking"] == {"type": "adaptive"}
    # Brand system prompt is sent as a cached block.
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["output_format"] is GeneratedContent


def test_generate_raises_when_no_structured_output(base_config):
    agent = ContentAgent(base_config)
    agent._client = MagicMock()
    agent._client.messages.parse.return_value = SimpleNamespace(
        parsed_output=None, stop_reason="refusal", usage=SimpleNamespace()
    )

    post = Post(pillar="Review", platform="twitter")
    with pytest.raises(RuntimeError):
        agent.generate(post)


def test_missing_api_key_raises():
    import dataclasses

    from core.config import ConfigError, config

    cfg = dataclasses.replace(config, anthropic_api_key=None)
    with pytest.raises(ConfigError):
        ContentAgent(cfg)
