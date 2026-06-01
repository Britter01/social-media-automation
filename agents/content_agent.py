"""Content agent — captions and hashtags via the Claude API.

Model choice: ``model_creative`` (Sonnet 4.6). Writing an on-brand caption
and hook is a creative task where quality directly shapes engagement, so it
warrants the mid-tier model — but not Opus, whose extra reasoning buys
little on short social copy at several times the cost. Hashtags are simple
enough for Haiku, but they're produced in the *same* structured response as
the caption: bundling them in costs only a few extra output tokens, which is
cheaper than a second (Haiku) round-trip with its own input + request
overhead. So the whole call stays on Sonnet.

Uses the Anthropic Python SDK with:
  * adaptive thinking, so Claude decides how hard to think per request;
  * prompt caching on the large, stable brand system prompt, so repeated
    generations across a run only pay full price for the first call;
  * structured outputs (`messages.parse`) validated against a Pydantic
    model, so we never hand-parse free-form text.

The brand voice and content-pillar guidance live in the cached system
prefix; only the per-request topic/platform varies, which is exactly the
shape prompt caching rewards.
"""

from __future__ import annotations

import logging

import anthropic
from pydantic import BaseModel, Field

from core.config import Config, config
from core.models import Post, PostStatus

logger = logging.getLogger(__name__)


class GeneratedContent(BaseModel):
    """Structured result Claude must return."""

    title: str = Field(description="A short, scroll-stopping title or hook.")
    caption: str = Field(description="The post caption in the brand voice.")
    hashtags: list[str] = Field(description="5-12 relevant hashtags WITHOUT the leading '#'.")


# Per-platform nuance the model should respect. Kept here (not in the cached
# prefix) only conceptually — it's small and stable so it stays in the prefix.
_PLATFORM_GUIDANCE = {
    "instagram": "Visual-first. 1-3 short paragraphs. A clear hook in line one. Up to 10 hashtags.",
    "twitter": "Under 280 characters total including hashtags. Punchy. 1-3 hashtags only.",
    "linkedin": (
        "Professional but warm. A strong opening line, short paragraphs, one insight. 3-5 hashtags."
    ),
    "youtube": (
        "Write a compelling video title and a description with a hook, "
        "value, and a soft CTA. 5-8 tags."
    ),
    "tiktok": (
        "Casual, energetic, native to short video. A hook in the first line. "
        "3-5 trending-style hashtags."
    ),
}


def _system_prompt(brand_name: str, founder: str, tagline: str, voice: str) -> str:
    """The large, stable brand brief that gets prompt-cached."""
    pillars = (
        "AI Guide — practical, accessible explainers that make AI useful today.\n"
        "Tech Lifestyle — how good technology fits into a well-lived life.\n"
        "Productivity — tools and systems that give people their time back.\n"
        "Fitness Tech — wearables, apps, and gear for a healthier life.\n"
        "Review — honest, hands-on verdicts. Pros, cons, who it's for."
    )
    return (
        f"You write social media content for {brand_name}, "
        f"founded by {founder}.\n"
        f'Tagline: "{tagline}"\n\n'
        f"BRAND VOICE: {voice}\n"
        "Write like you respect the reader's intelligence and time. "
        "Lead with value. No hype, no filler, no emoji spam. "
        "Avoid clichés like 'game-changer', 'unlock', 'dive in', 'in today's world'.\n\n"
        "CONTENT PILLARS:\n"
        f"{pillars}\n\n"
        "Every caption must be original, specific, and immediately useful or "
        "interesting. Hashtags should be relevant and a mix of broad and niche. "
        "Never fabricate product specs, prices, or claims."
    )


class ContentAgent:
    """Generates a caption, title, and hashtags for a post."""

    def __init__(self, cfg: Config = config) -> None:
        cfg.require("anthropic_api_key")
        self._cfg = cfg
        self._client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        self._system = _system_prompt(
            cfg.brand_name,
            cfg.brand_founder,
            cfg.brand_tagline,
            "Clear, confident, warm. Never patronising. Short sentences.",
        )

    def generate(self, post: Post) -> Post:
        """Populate ``post`` with title, caption, and hashtags in place.

        Raises on hard API failures (auth, bad request) so the caller can
        decide whether to retry or mark the post failed.
        """
        guidance = _PLATFORM_GUIDANCE.get(post.platform, "Write a clear, engaging caption.")
        user_prompt = (
            f"Create a post for the '{post.pillar}' pillar, "
            f"for {post.platform.upper()}.\n"
            f"Topic: {post.topic or 'choose a strong, on-brand topic for this pillar'}.\n\n"
            f"Platform guidance: {guidance}\n\n"
            "Return a title/hook, the caption, and hashtags."
        )

        try:
            response = self._client.messages.parse(
                # Creative tier (Sonnet): caption writing is the quality-
                # sensitive part of the pipeline; hashtags ride along.
                model=self._cfg.model_creative,
                max_tokens=2000,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                system=[
                    {
                        "type": "text",
                        "text": self._system,
                        # Cache the stable brand brief — every generation in a
                        # run reuses it at ~0.1x cost.
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_prompt}],
                output_format=GeneratedContent,
            )
        except anthropic.APIError:
            logger.exception(
                "Content generation failed for post %s (%s/%s)",
                post.id,
                post.pillar,
                post.platform,
            )
            raise

        result: GeneratedContent | None = response.parsed_output
        if result is None:
            # Refusal or schema mismatch — surface it rather than guess.
            raise RuntimeError(
                f"Claude returned no structured content (stop_reason={response.stop_reason})"
            )

        post.title = result.title.strip()
        post.caption = result.caption.strip()
        post.hashtags = [h.lstrip("#").strip() for h in result.hashtags if h.strip()]
        post.mark(PostStatus.CONTENT_READY)

        usage = response.usage
        logger.info(
            "Generated content for post %s (%s/%s) | cache_read=%s input=%s output=%s",
            post.id,
            post.pillar,
            post.platform,
            getattr(usage, "cache_read_input_tokens", 0),
            usage.input_tokens,
            usage.output_tokens,
        )
        return post
