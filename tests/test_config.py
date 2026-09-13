"""Tests for core.config."""

from __future__ import annotations

import pytest

from core.config import Config, ConfigError


def test_require_raises_for_missing_keys():
    cfg = Config()  # all credentials default to None
    with pytest.raises(ConfigError) as exc:
        cfg.require("anthropic_api_key", "supabase_url")
    # The error names the missing env vars in upper case.
    assert "ANTHROPIC_API_KEY" in str(exc.value)
    assert "SUPABASE_URL" in str(exc.value)


def test_require_passes_when_present(base_config):
    # Should not raise.
    base_config.require("anthropic_api_key", "supabase_url", "supabase_key")


def test_from_env_reads_values(monkeypatch):
    monkeypatch.setenv("BRAND_NAME", "Test Brand")
    monkeypatch.setenv("POSTS_PER_RUN", "3")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "  spaced-key  ")

    cfg = Config.from_env()
    assert cfg.brand_name == "Test Brand"
    assert cfg.posts_per_run == 3
    assert cfg.dry_run is True
    # Values are stripped of surrounding whitespace.
    assert cfg.anthropic_api_key == "spaced-key"


def test_configured_platforms_filters_to_credentialed(base_config):
    import dataclasses

    # Only instagram + facebook + twitter credentials present.
    cfg = dataclasses.replace(
        base_config,
        linkedin_access_token=None,
        youtube_refresh_token=None,
        tiktok_access_token=None,
    )
    assert cfg.configured_platforms() == ["instagram", "facebook", "twitter"]


def test_default_pillars_and_platforms():
    cfg = Config()
    assert cfg.content_pillars == [
        "AI Guide",
        "Tech Lifestyle",
        "Productivity",
        "Fitness Tech",
        "Review",
    ]
    assert "tiktok" in cfg.platforms


def test_retired_imagen_model_env_is_ignored(monkeypatch):
    """IMAGEN_MODEL still points at a shut-down model in deployed envs.

    Google retired the imagen-* models on 17 Aug 2026, so honouring that
    variable would 404 on every image. It must be ignored, not obeyed.
    """
    from core.config import _DEFAULT_IMAGE_MODEL, _image_model_from_env

    monkeypatch.delenv("IMAGE_MODEL", raising=False)
    monkeypatch.setenv("IMAGEN_MODEL", "imagen-4.0-generate-001")
    assert _image_model_from_env() == _DEFAULT_IMAGE_MODEL


def test_explicit_image_model_wins(monkeypatch):
    from core.config import _image_model_from_env

    monkeypatch.setenv("IMAGE_MODEL", "gemini-3.1-flash-image")
    monkeypatch.setenv("IMAGEN_MODEL", "imagen-4.0-generate-001")
    assert _image_model_from_env() == "gemini-3.1-flash-image"


def test_non_imagen_legacy_value_is_respected(monkeypatch):
    # Only imagen-* is retired; anything else the user set is still their choice.
    from core.config import _image_model_from_env

    monkeypatch.delenv("IMAGE_MODEL", raising=False)
    monkeypatch.setenv("IMAGEN_MODEL", "gemini-2.5-flash-image")
    assert _image_model_from_env() == "gemini-2.5-flash-image"
