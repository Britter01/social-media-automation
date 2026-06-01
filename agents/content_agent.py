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


# Per-platform rules. These are stable, so they live inside the cached system
# brief (rendered by `_system_prompt`) rather than the per-request user prompt —
# that keeps the volatile part of the request tiny and the cached prefix large.
_PLATFORM_GUIDANCE = {
    "instagram": (
        "Visual-first. 1-3 short paragraphs. A clear hook in line one that works "
        "without the image. Conversational. End with a light question or CTA. Up "
        "to 10 hashtags, a mix of broad and niche."
    ),
    "twitter": (
        "Under 280 characters total INCLUDING hashtags. One sharp idea, no wind-up. "
        "Punchy, plain words. 1-3 hashtags only — often zero reads better."
    ),
    "linkedin": (
        "Professional but warm, never corporate. A strong standalone opening line, "
        "then short paragraphs (1-2 sentences each) building to one concrete insight "
        "or takeaway. No engagement-bait. 3-5 hashtags."
    ),
    "youtube": (
        "Write a compelling, specific video title (front-load the value, avoid "
        "ALL-CAPS clickbait) and a description with a one-line hook, the value the "
        "video delivers, and a soft CTA. 5-8 tags."
    ),
    "tiktok": (
        "Casual, energetic, native to short video. A pattern-breaking hook in the "
        "first line. Speak to one person. 3-5 trending-style hashtags."
    ),
}

# Worked examples that anchor the voice. They're stable, so they stay in the
# cached prefix; concrete examples lift quality far more than abstract rules.
# One per pillar, spread across platforms, so the model sees the voice in every
# context it writes for.
_EXAMPLES = (
    "Pillar: Productivity / linkedin\n"
    'Title: "The two-minute rule is quietly ruining your focus"\n'
    "Caption: Doing every small task the moment it appears feels productive. "
    "It isn't. Each interruption costs ~23 minutes of refocus time, so ten "
    '"quick" replies can eat your whole afternoon.\n\n'
    "Batch them instead. One slot late morning, one mid-afternoon. The world "
    "keeps turning, and your deep work survives.\n"
    "Hashtags: productivity, focus, deepwork, timemanagement, worksmarter\n\n"
    "Pillar: Fitness Tech / instagram\n"
    'Title: "Your sleep score is lying to you"\n'
    "Caption: Wearables guess sleep stages from movement and heart rate — useful "
    'for trends, not gospel. A single "bad" night rarely means what the number '
    "says.\n\n"
    "Watch the weekly direction, not the daily score. That's where the signal is.\n"
    "Hashtags: fitnesstech, wearables, sleep, recovery, healthtech\n\n"
    "Pillar: Review / twitter\n"
    'Title: "Honest take after 3 weeks"\n'
    "Caption: Three weeks with these earbuds: the noise cancelling is genuinely "
    "great, the app is a mess, battery beats the claim. Worth it if ANC is your "
    "priority, skip if you live in the app.\n"
    "Hashtags: techreview, audio\n\n"
    "Pillar: AI Guide / youtube\n"
    'Title: "Stop pasting your whole doc into ChatGPT — do this instead"\n'
    "Caption: Dumping a 20-page document into a chatbot and asking for a summary "
    "is the slowest, least accurate way to use it. In this video: how to ask for "
    "a structured outline first, then drill into the sections that matter — so you "
    "get answers you can actually trust. Try it on your next report and tell me "
    "how it goes.\n"
    "Hashtags: ai, chatgpt, productivity, aitools, howto, promptengineering\n\n"
    "Pillar: Tech Lifestyle / instagram\n"
    'Title: "The best phone setting is the one that hides your phone"\n'
    "Caption: A greyscale home screen sounds gimmicky. It isn't. Stripping the "
    "colour off your apps removes the tiny dopamine pulls that make you pick the "
    "phone up without deciding to.\n\n"
    "Five minutes in Accessibility settings. Your evenings feel longer by Friday.\n"
    "Hashtags: techlifestyle, digitalwellbeing, focus, mindfultech, screentime\n\n"
    "Pillar: Productivity / tiktok\n"
    'Title: "The 10-minute rule that killed my to-do list anxiety"\n'
    "Caption: Can't start a task? Promise yourself ten minutes. That's it. Starting "
    "is the hard part — once you're in, you usually keep going. And if you don't, "
    "ten minutes still beats zero.\n"
    "Hashtags: productivity, motivation, adhd, studytok\n\n"
    "Pillar: Review / youtube\n"
    "Title: \"I tested the budget smartwatch everyone's buying. Here's the catch.\"\n"
    "Caption: It nails the basics — bright screen, solid step and heart-rate "
    "tracking, a week of battery. The catch: notifications are unreliable and the "
    "GPS drifts on runs. If you want a cheap activity tracker, great. If you want a "
    "running watch, keep saving. Full breakdown and who it's for in the video.\n"
    "Hashtags: techreview, smartwatch, wearables, fitnesstech, budgettech\n\n"
    "Pillar: AI Guide / linkedin\n"
    'Title: "AI won\'t take your job. Someone using it badly might cost you yours."\n'
    "Caption: The real risk isn't the model — it's shipping its output unchecked. "
    "AI is brilliant at a confident first draft and terrible at knowing when it's "
    "wrong.\n\n"
    "Treat it like a fast junior: great for momentum, never the final reviewer. "
    "The people who win with it are the ones who still read every line.\n"
    "Hashtags: ai, futureofwork, productivity, leadership\n\n"
    "Pillar: Tech Lifestyle / youtube\n"
    'Title: "I gave my devices a bedtime. My sleep changed in a week."\n'
    "Caption: Not a detox, not throwing the phone in a drawer — just a hard "
    "charging cut-off in another room after 10pm. The first two nights were "
    "fidgety. By night five I was reading again. Here's the exact setup and the "
    "two settings that made it stick.\n"
    "Hashtags: techlifestyle, digitalwellbeing, sleep, habits, mindfultech\n\n"
    "Pillar: Fitness Tech / twitter\n"
    'Title: "Reading your resting heart rate right"\n'
    "Caption: One high resting-HR morning isn't a warning. A 5-day climb is. "
    "Wearables are trend instruments, not diagnoses — watch the slope, not the dot.\n"
    "Hashtags: fitnesstech, recovery\n"
)


def _system_prompt(brand_name: str, founder: str, tagline: str, voice: str) -> str:
    """The large, stable brand brief that gets prompt-cached.

    Deliberately substantial: it carries the full voice guide, pillar and
    per-platform rules, and worked examples. That serves two ends at once —
    it produces better, more consistent copy, and it makes the cached prefix
    comfortably exceed Sonnet's ~2048-token minimum, so the `cache_control`
    breakpoint actually fires and every generation after the first in a batch
    reuses it at ~0.1x cost. Keep it byte-stable (no timestamps/IDs) or the
    cache won't hit.
    """
    pillars = (
        "AI Guide — practical, accessible explainers that make AI useful today. "
        "Translate hype into what someone can actually do this week.\n"
        "Tech Lifestyle — how good technology fits into a well-lived life: calm, "
        "intentional, human. Tech in service of living, not the other way round.\n"
        "Productivity — tools and systems that give people their time back. "
        "Concrete tactics over motivation.\n"
        "Fitness Tech — wearables, apps, and gear for a healthier life. Evidence "
        "over fads; honest about what the data can and can't tell you.\n"
        "Review — honest, hands-on verdicts. Pros, cons, and exactly who it's for. "
        "Never a press release."
    )
    platforms = "\n".join(f"{name} — {rules}" for name, rules in _PLATFORM_GUIDANCE.items())
    return (
        f"You write social media content for {brand_name}, founded by {founder}.\n"
        f'Tagline: "{tagline}"\n\n'
        "AUDIENCE: curious, time-poor people who like technology but are tired of "
        "hype and noise. They're smart but not necessarily specialists; they want "
        "to know what's worth their attention and what to actually do about it. "
        "Write for one of them at a time, not a crowd.\n\n"
        f"BRAND VOICE: {voice}\n"
        "Write like you respect the reader's intelligence and time. Lead with "
        "value in the first line. Prefer concrete specifics (numbers, names, "
        "trade-offs) over vague enthusiasm. Short sentences. Plain words over "
        "jargon. One idea per post. No hype, no filler, no emoji spam (one is "
        "plenty, often none). Sound like a knowledgeable friend, not a brand "
        "account.\n\n"
        "HOOKS: the first line has to earn the second. Make a specific claim, "
        "name a tension, or promise a concrete payoff — never warm up with "
        "throat-clearing. Strong shapes: a counter-intuitive claim ('Your sleep "
        "score is lying to you'), a specific number ('23 minutes to refocus'), a "
        "named mistake ('Stop pasting your whole doc into ChatGPT'), or a plain "
        "promise of value. Weak openers to avoid: 'In today's world…', 'Have you "
        "ever wondered…', 'Let's be honest…', 'We're excited to…'.\n\n"
        "NEVER use these clichés or their cousins: 'game-changer', 'unlock', "
        "'dive in', 'in today's world', 'take it to the next level', 'revolutionary', "
        "'seamless', 'supercharge', 'must-have', 'level up', 'thrilled to announce'. "
        "Don't open with a rhetorical question or 'Let's be honest'. Don't end with "
        "a string of hashtags masquerading as a sentence.\n\n"
        "ACCURACY: Never fabricate product specs, prices, dates, study results, or "
        "quotes. If a detail isn't given in the topic, write around it rather than "
        "inventing it. It's better to be slightly less specific than to be wrong.\n\n"
        "CONTENT PILLARS:\n"
        f"{pillars}\n\n"
        "PLATFORM RULES (write natively for the requested platform):\n"
        f"{platforms}\n\n"
        "LENGTH TARGETS (rough, not rigid): instagram 50-125 words; twitter/X one "
        "tight thought under 280 characters including hashtags; linkedin 50-120 "
        "words across 2-4 short paragraphs; youtube a punchy title plus a 40-90 word "
        "description; tiktok a spoken-feeling 2-5 short lines. When in doubt, "
        "shorter and sharper beats longer.\n\n"
        "HASHTAGS: relevant and specific, a mix of broad reach and niche intent. "
        "Return them WITHOUT the leading '#'. Match the count to the platform rule "
        "above. Never stuff or repeat near-duplicates.\n\n"
        "STRUCTURE EVERY POST AS: a title/hook that earns the first second of "
        "attention, a caption that delivers one genuinely useful or interesting "
        "idea, then hashtags. Make it original and specific to the topic — if it "
        "could have been written about any product, it's too generic.\n\n"
        "CTAs: optional, and never pushy. A light question or a single clear next "
        "step beats 'Follow for more!' or 'Link in bio!!!'. On LinkedIn and X a CTA "
        "is often better left off entirely — let the insight stand.\n\n"
        "COMMON MISTAKES TO SELF-CHECK BEFORE RETURNING:\n"
        "- The hook is generic or could front any brand's post → rewrite it specific.\n"
        "- More than one idea crammed in → cut to the strongest one.\n"
        "- A claim with a number or spec you weren't given → remove or soften it.\n"
        "- Hashtags repeat the caption's words or each other → diversify.\n"
        "- It reads like marketing → make it read like a useful tip from a friend.\n"
        "- Twitter/X post over 280 chars including hashtags → trim.\n\n"
        "REWRITES (weak → strong, learn the difference):\n"
        "WEAK: 'In today's fast-paced world, productivity is more important than "
        "ever. Here are some game-changing tips to supercharge your workflow!'\n"
        "STRONG: 'You don't have a productivity problem. You have a too-many-open-"
        "tabs problem. Close all but three. Watch what happens to your afternoon.'\n\n"
        "WEAK: 'We're thrilled to dive into the world of AI! These revolutionary "
        "tools will unlock your potential and take your work to the next level.'\n"
        "STRONG: 'Most people use AI like a search engine. The trick is to make it "
        "argue with itself: ask for the answer, then ask it to find three holes in "
        "that answer. The second pass is where the value is.'\n\n"
        "WEAK: 'This amazing must-have gadget is a seamless game-changer you "
        "absolutely need in your life right now!'\n"
        "STRONG: 'It does one thing — charges three devices from a single, "
        "pocket-sized brick — and it does it well. If you travel light, it earns "
        "its place. If you don't, skip it.'\n\n"
        "WORKED EXAMPLES (match this voice and shape, not the exact topics):\n"
        f"{_EXAMPLES}"
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
        # Keep the user turn tiny: all the stable guidance (voice, pillars,
        # platform rules, examples) is in the cached system brief, so only the
        # genuinely varying bits go here.
        user_prompt = (
            f"Create a post for the '{post.pillar}' pillar, for {post.platform.upper()}.\n"
            f"Topic: {post.topic or 'choose a strong, on-brand topic for this pillar'}.\n\n"
            "Apply the brand voice, pillar guidance, and platform rules from your "
            "brief. Return a title/hook, the caption, and hashtags."
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
                        # Cache the brand brief. It's sized to clear Sonnet's
                        # ~2048-token cache minimum, so within a batch of posts
                        # the first call writes it (~1.25x) and the rest read it
                        # (~0.1x) instead of re-paying full price each time.
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
