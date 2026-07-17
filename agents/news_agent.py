"""Daily AI News Carousel agent.

Fetches today's top 3 AI news stories via web search, selects and summarises
them with Claude, and renders a 5-slide branded carousel:

  Slide 1 — Cover: "Today in AI" + date
  Slide 2 — Story 1 (headline + summary + why it matters)
  Slide 3 — Story 2
  Slide 4 — Story 3
  Slide 5 — CTA: follow for daily AI briefings

Uses the same dark text-card rendering as the carousel agent so the visual
style is consistent with all other Brite Tech Lifestyle carousel posts.
"""

from __future__ import annotations

import logging
import uuid as _uuid

import anthropic
from pydantic import BaseModel, Field

from core.config import Config, config
from core.models import Platform, Post, PostStatus

logger = logging.getLogger(__name__)

_WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 8,
}
_MAX_WEB_TURNS = 5

# Brite Blue abstract background for the news carousel — same rich AI aesthetic
# as the infographics, kept in the brand's accent blue. Generated once via
# Higgsfield (Imagen fallback), then stored as a reusable template.
_NEWS_BG_PROMPT = (
    "abstract AI neural network background, deep Brite Blue and electric cobalt tones, "
    "glowing interconnected nodes and luminous data trails, dark navy cosmic depth, "
    "subtle geometric grid lines, cinematic volumetric light, rich saturated blue gradient, "
    "premium editorial tech aesthetic, 3D depth, no text, no letters, no words"
)


class NewsStory(BaseModel):
    headline: str = Field(description="News headline — max 10 words, factual, no hype, no emojis.")
    summary: str = Field(
        description=(
            "Short version for the carousel SLIDE — 1-2 factual sentences. "
            "Include key names and figures. No emojis."
        )
    )
    insight: str = Field(
        description="Why it matters to everyday tech users — 1 sentence, max 12 words. No emojis."
    )
    full_text: str = Field(
        description=(
            "The FULL write-up for the CAPTION (not the slide) — the complete story the "
            "reader finishes below the images. 3-5 sentences: what happened, the key "
            "specifics (companies, numbers, dates, names), and why it matters in plain "
            "language. Self-contained and readable on its own. No emojis, no hashtags."
        )
    )


class NewsCarouselPlan(BaseModel):
    lead_headline: str = Field(
        description="Cover slide headline — e.g. 'Today in AI'. Max 6 words, punchy, no emojis."
    )
    caption: str = Field(
        description=(
            "A warm 1-2 sentence INTRO that opens the caption — sets up today's AI "
            "briefing. The full stories are appended after it automatically, so do NOT "
            "summarise the stories here. No hashtags, no emojis."
        )
    )
    closing_question: str = Field(
        description=(
            "One light engagement question to end the caption — invites a reply. "
            "No hashtags, no emojis."
        )
    )
    hashtags: list[str] = Field(
        description=(
            "Exactly 5 relevant hashtags WITHOUT the # prefix. "
            "Mix: AINews, ArtificialIntelligence + 3 topic-specific niche tags."
        )
    )
    stories: list[NewsStory] = Field(
        description=(
            "Exactly 3 top AI news stories from today's research, ordered by importance. "
            "All three MUST be populated — never leave any story out."
        )
    )


class NewsAgent:
    """Fetches today's top AI news and produces a branded daily news carousel."""

    def __init__(self, cfg: Config = config) -> None:
        cfg.require("anthropic_api_key")
        self._cfg = cfg
        self._client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

        self._storage = None
        if cfg.supabase_url and cfg.supabase_key:
            try:
                from core.storage import get_storage

                self._storage = get_storage(cfg)
            except Exception:
                logger.warning("NewsAgent: Supabase Storage unavailable", exc_info=True)

    _BG_TEMPLATE_PATH = "templates/news_carousel_bg.png"

    def _get_bg_template(self) -> bytes | None:
        """Return the news-carousel background template bytes.

        First run: generate a rich Brite Blue abstract background via Higgsfield
        (Imagen fallback), bake in the readability gradient, and upload to
        Supabase. Every subsequent run is a fast download of that template.
        If no image API is available, falls back to a pure Pillow gradient.
        Returns None only when storage is unavailable AND no fallback renders.
        """
        from core.image_utils import make_news_bg_template

        # Persistent template hit — reuse the stored background, no generation.
        if self._storage is not None:
            try:
                cached = self._storage.download(self._BG_TEMPLATE_PATH)
                if cached:
                    logger.info("NewsAgent: using stored background template")
                    return cached
            except Exception:
                logger.warning("NewsAgent: template download failed", exc_info=True)

        # First run (or storage miss) — generate the AI base, bake the template.
        logger.info("NewsAgent: generating background template for the first time")
        ai_base = self._generate_ai_background()
        try:
            template = make_news_bg_template(base_bytes=ai_base)
        except Exception:
            logger.exception("NewsAgent: failed to bake background template")
            return None

        if self._storage is not None:
            try:
                self._storage.upload(self._BG_TEMPLATE_PATH, template, content_type="image/png")
                logger.info("NewsAgent: background template stored at %s", self._BG_TEMPLATE_PATH)
            except Exception:
                logger.warning("NewsAgent: failed to store background template", exc_info=True)

        return template

    def _generate_ai_background(self) -> bytes | None:
        """Generate a Brite Blue abstract background via Higgsfield (Imagen fallback).

        Returns the raw image bytes, or None if no image API is configured or
        both providers fail — in which case the caller bakes a pure gradient.
        """
        if not (self._cfg.higgsfield_api_key or self._cfg.google_api_key):
            logger.info("NewsAgent: no image API configured — using gradient background")
            return None

        try:
            from agents.infographic_agent import InfographicAgent

            ia = InfographicAgent(self._cfg)
        except Exception:
            logger.warning("NewsAgent: could not init image agent for background", exc_info=True)
            return None

        if self._cfg.higgsfield_api_key:
            try:
                logger.info("NewsAgent: generating background via Higgsfield")
                return ia._higgsfield_background(aspect_ratio="1:1", prompt=_NEWS_BG_PROMPT)
            except Exception:
                logger.warning(
                    "NewsAgent: Higgsfield background failed; trying Imagen", exc_info=True
                )

        if self._cfg.google_api_key:
            try:
                logger.info("NewsAgent: generating background via Imagen")
                return ia._imagen_background(aspect_ratio="1:1", prompt=_NEWS_BG_PROMPT)
            except Exception:
                logger.warning("NewsAgent: Imagen background failed", exc_info=True)

        return None

    # ── Public API ────────────────────────────────────────────────────────────

    def create_news_carousel(self, platforms: list[str] | None = None) -> list[Post]:
        """Fetch today's top AI news and return carousel Posts ready for scheduling."""
        if platforms is None:
            configured = set(self._cfg.configured_platforms())
            platforms = [
                p for p in [Platform.INSTAGRAM.value, Platform.FACEBOOK.value] if p in configured
            ] or [Platform.INSTAGRAM.value]

        logger.info("NewsAgent: fetching today's AI news via web search")
        research = self._fetch_ai_news()

        logger.info("NewsAgent: planning news carousel")
        plan = self._plan_news(research)
        logger.info(
            "NewsAgent: planned '%s' with %d stories", plan.lead_headline, len(plan.stories)
        )

        carousel_id = str(_uuid.uuid4())
        slides_data = self._render_slides(carousel_id, plan)
        if not slides_data:
            raise RuntimeError("NewsAgent: no slides were rendered")

        caption = self._build_caption(plan)
        hashtags = [h.lstrip("#").strip() for h in plan.hashtags[:5]]

        posts: list[Post] = []
        for plat in platforms:
            post = Post(
                id=str(_uuid.uuid4()),
                pillar="AI News",
                platform=plat,
                topic="AI News",
                title=plan.lead_headline,
                caption=caption,
                hashtags=hashtags,
                post_type="carousel",
                slides=slides_data,
                thumbnail_url=slides_data[0]["image_url"] if slides_data else "",
                status=PostStatus.MEDIA_READY.value,
            )
            posts.append(post)
            logger.info("NewsAgent: created %s news carousel %s", plat, post.id)

        return posts

    # ── Internals ─────────────────────────────────────────────────────────────

    def _fetch_ai_news(self) -> str:
        """Fetch today's top AI news stories via multi-turn web search."""
        from datetime import UTC, datetime

        today = datetime.now(UTC).strftime("%A, %B %d, %Y")
        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Today is {today}. Search for the 5 most important AI news stories "
                    "published in the last 24-48 hours. Look for: major model releases, "
                    "company announcements, research breakthroughs, regulatory news, "
                    "or significant funding rounds. "
                    "Report AT LEAST 5 distinct stories so the editor can pick the best "
                    "three — for EACH story give: what happened, who was involved, and "
                    "specific facts (numbers, dates, names, quotes) in a full paragraph. "
                    "Prioritise novelty and impact."
                ),
            }
        ]

        response = None
        for _ in range(_MAX_WEB_TURNS):
            response = self._client.messages.create(
                model=self._cfg.model_creative,
                max_tokens=4000,
                tools=[_WEB_SEARCH_TOOL],
                messages=messages,
            )
            if response.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": response.content})

        if response is None:
            raise RuntimeError("NewsAgent: web search produced no response")

        return "\n".join(getattr(b, "text", "") for b in response.content if hasattr(b, "text"))

    @staticmethod
    def _valid_stories(stories) -> list:
        """Return only stories with a real headline AND body (full_text/summary).

        The model occasionally returns a third story with empty fields; those
        must never reach the caption ("3." with nothing) or a blank slide.
        """
        out = []
        for s in stories[:3]:
            headline = (getattr(s, "headline", "") or "").strip()
            body = (getattr(s, "full_text", "") or getattr(s, "summary", "") or "").strip()
            if headline and body:
                out.append(s)
        return out

    def _plan_news_attempt(self, raw_research: str, reminder: str = "") -> NewsCarouselPlan:
        plan_tool = {
            "name": "create_news_carousel_plan",
            "description": "Create a daily AI news carousel plan from web research.",
            "input_schema": NewsCarouselPlan.model_json_schema(),
        }
        response = self._client.messages.create(
            model=self._cfg.model_creative,
            # Generous budget: three full-text write-ups plus the summaries,
            # insights, intro, question and hashtags must all fit, or the last
            # story comes back empty.
            max_tokens=6000,
            system=(
                f"You are the content editor for {self._cfg.brand_name} — "
                f'"{self._cfg.brand_tagline}". '
                "Voice: clear, confident, warm. Short sentences. Never patronising. "
                "You are creating a daily AI news carousel for Instagram and Facebook. "
                "Select the 3 most important and interesting AI stories from the research. "
                "Be specific — include company names, numbers, and dates. "
                "Each story insight must explain WHY it matters to everyday tech users "
                "in plain language. No jargon. No hype. Make it feel like a trusted friend "
                "sharing the day's news over coffee.\n\n"
                "IMPORTANT — two versions of each story:\n"
                "- 'summary' is the SHORT version shown on the carousel image (1-2 "
                "sentences, tight).\n"
                "- 'full_text' is the FULL write-up shown in the caption — 3-5 sentences "
                "so the reader can finish the story the slide only teased. Do not just "
                "repeat the summary; give the fuller picture with the specifics and the "
                "so-what.\n"
                "ALL THREE stories must be fully populated — headline, summary, insight, "
                "AND full_text. Never leave the third story blank; keep each full_text "
                "tight (3-4 sentences) so all three comfortably fit. The caption intro "
                "should NOT summarise the stories (they are appended in full "
                "automatically); keep it to a warm 1-2 sentence opener."
            ),
            tools=[plan_tool],
            tool_choice={"type": "tool", "name": "create_news_carousel_plan"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Research:\n{raw_research}\n\n"
                        "The research above contains several candidate stories. Pick the "
                        "THREE strongest and write EACH one up completely — every one of "
                        "the three needs a full headline, summary, insight and full_text. "
                        "The third story matters just as much as the first: do not run out "
                        "of steam and leave it thin or empty. Return exactly 3 complete "
                        "stories." + reminder
                    ),
                }
            ],
        )
        for block in response.content:
            if (
                getattr(block, "type", None) == "tool_use"
                and block.name == "create_news_carousel_plan"
            ):
                return NewsCarouselPlan(**block.input)
        raise RuntimeError("NewsAgent: news carousel plan tool call returned no result")

    def _plan_news(self, raw_research: str) -> NewsCarouselPlan:
        """Ask Claude to extract 3 stories and build the carousel plan.

        Retries once if the model returns fewer than 3 complete stories, then
        keeps whichever attempt was most complete (downstream renders only the
        valid stories, so a partial result is still clean — never a blank slot).
        """
        plan = self._plan_news_attempt(raw_research)
        if len(self._valid_stories(plan.stories)) >= 3:
            return plan
        logger.warning("NewsAgent: plan had <3 complete stories — retrying once")
        plan2 = self._plan_news_attempt(
            raw_research,
            reminder=(
                "\n\nYOUR LAST ATTEMPT LEFT A STORY INCOMPLETE. This time, make sure "
                "ALL THREE stories have a non-empty headline, summary, insight and "
                "full_text. Keep each full_text to 3 tight sentences so all three fit."
            ),
        )
        return (
            plan2
            if len(self._valid_stories(plan2.stories)) >= len(self._valid_stories(plan.stories))
            else plan
        )

    def _render_slides(self, carousel_id: str, plan: NewsCarouselPlan) -> list[dict]:
        """Render 5 branded text cards and upload each to Supabase storage."""
        import re
        from datetime import UTC, datetime

        from core.image_utils import add_brand_overlay, make_dark_text_card

        def _clean(text: str) -> str:
            """Strip emoji and non-BMP characters the brand font cannot render."""
            return re.sub(r"[^\x00-\xFF -⁯℀-⅏]", "", text).strip()

        # Date goes IN the cover headline so it renders large next to the title
        # (e.g. "TODAY IN AI: JULY 15"), not as small subtitle text.
        _date_headline = datetime.now(UTC).strftime("%B %-d").upper()  # "JULY 15"
        # Only render stories that are actually populated — an empty third story
        # must not produce a blank slide or an inflated "3 stories" count.
        _stories = self._valid_stories(plan.stories)
        if not _stories:
            raise RuntimeError("NewsAgent: plan produced no complete stories")
        _story_count = len(_stories)
        _story_word = "story" if _story_count == 1 else "stories"

        all_slides = [
            {
                "headline": _clean(f"{plan.lead_headline}: {_date_headline}").upper(),
                "body": f"{_story_count} {_story_word} shaping AI today",
                "role": "cover",
                "slide_number": None,
            },
        ]
        for i, story in enumerate(_stories, 1):
            all_slides.append(
                {
                    "headline": _clean(story.headline),
                    "body": _clean(f"{story.summary}\n\nWhy it matters: {story.insight}"),
                    "role": "content",
                    "slide_number": i,
                }
            )
        all_slides.append(
            {
                "headline": "Follow for Daily AI News",
                "body": (
                    f"Get your daily AI briefing from {self._cfg.brand_name}. "
                    "Follow to stay ahead of the curve."
                ),
                "role": "cta",
                "slide_number": None,
            }
        )

        # Fetch (or generate on first run) the shared gradient background template.
        bg_bytes = self._get_bg_template()

        result: list[dict] = []
        for idx, slide in enumerate(all_slides):
            try:
                image_bytes = make_dark_text_card(
                    headline=slide["headline"],
                    body=slide["body"],
                    slide_number=slide["slide_number"],
                    brand_name=self._cfg.brand_name,
                    brand_tagline=self._cfg.brand_tagline,
                    theme="blue",
                    bg_bytes=bg_bytes,
                )
                image_bytes = add_brand_overlay(
                    image_bytes,
                    self._cfg.brand_name,
                    self._cfg.brand_tagline,
                    corner="top_right",
                    crop_bars=False,
                )
                url = self._upload(carousel_id, idx, image_bytes)
                result.append(
                    {
                        "headline": slide["headline"],
                        "body": slide["body"],
                        "role": slide["role"],
                        "image_url": url,
                    }
                )
            except Exception as exc:
                # Fail the whole run rather than publish an incomplete carousel —
                # a missing story slide (or worse, a missing cover) would go out
                # silently. The command queue surfaces the error with a retry.
                logger.exception("NewsAgent: failed to render/upload slide %d", idx)
                raise RuntimeError(
                    f"news carousel slide {idx} ({slide['role']}) failed: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

        return result

    def _upload(self, carousel_id: str, slide_index: int, image_bytes: bytes) -> str:
        if self._storage is None:
            raise RuntimeError(
                "Supabase Storage not configured — check SUPABASE_URL and SUPABASE_KEY"
            )
        path = f"carousels/{carousel_id}/slide_{slide_index:02d}.png"
        return self._storage.upload(path, image_bytes, content_type="image/png")

    @staticmethod
    def _build_caption(plan: NewsCarouselPlan) -> str:
        """Compose the full caption: intro + each story written up in full + question.

        The carousel slides only have room for a headline and a line or two, so
        the caption carries the complete write-up of every story — the reader
        finishes each story here rather than being left with the teaser.
        """
        parts: list[str] = []
        intro = (plan.caption or "").strip()
        if intro:
            parts.append(intro)

        # Only include complete stories, re-numbered so there's never a "3."
        # with nothing after it when the model leaves a story empty.
        for i, story in enumerate(NewsAgent._valid_stories(plan.stories), 1):
            headline = (story.headline or "").strip()
            body = (getattr(story, "full_text", "") or story.summary or "").strip()
            block = f"{i}. {headline}".rstrip()
            if body:
                block += f"\n{body}"
            parts.append(block)

        closing = (getattr(plan, "closing_question", "") or "").strip()
        if closing:
            parts.append(closing)

        caption = "\n\n".join(parts).strip()

        # Instagram caps captions at 2200 chars (and ~5 hashtags are appended
        # later). Keep a safety margin so a verbose run can never hard-fail a
        # publish; trim at a sentence/word boundary rather than mid-word.
        _MAX = 2000
        if len(caption) > _MAX:
            cut = caption[:_MAX]
            for sep in (". ", "\n", " "):
                idx = cut.rfind(sep)
                if idx > _MAX * 0.6:
                    cut = cut[: idx + (1 if sep == ". " else 0)]
                    break
            caption = cut.rstrip() + " …"
        return caption
