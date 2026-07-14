"""Tests for the daily AI news carousel caption composition."""

from agents.news_agent import NewsAgent, NewsCarouselPlan, NewsStory


def _story(n: int) -> NewsStory:
    return NewsStory(
        headline=f"Headline {n}",
        summary=f"Short slide summary {n}.",
        insight=f"Why it matters {n}.",
        full_text=f"Full write-up sentence one for story {n}. Sentence two with a figure. "
        f"Sentence three on why it matters to everyday users.",
    )


def _plan() -> NewsCarouselPlan:
    return NewsCarouselPlan(
        lead_headline="Today in AI",
        caption="A warm opening line for today's briefing.",
        closing_question="Which story matters most to you?",
        hashtags=["AINews", "AI", "Tech", "OpenAI", "Anthropic"],
        stories=[_story(1), _story(2), _story(3)],
    )


def test_caption_includes_full_text_of_every_story():
    caption = NewsAgent._build_caption(_plan())
    # Intro and closing question are present…
    assert "A warm opening line" in caption
    assert caption.rstrip().endswith("Which story matters most to you?")
    # …and each story's FULL write-up is present (not just the slide summary).
    for n in (1, 2, 3):
        assert f"Full write-up sentence one for story {n}." in caption
        assert "Sentence three on why it matters to everyday users." in caption
    # Numbered per story.
    assert "1. Headline 1" in caption
    assert "3. Headline 3" in caption


def test_caption_is_trimmed_below_instagram_limit():
    long_story = NewsStory(
        headline="Long",
        summary="s",
        insight="i",
        full_text="word " * 800,  # ~4000 chars — well over the Instagram cap
    )
    plan = NewsCarouselPlan(
        lead_headline="Today in AI",
        caption="Intro.",
        closing_question="Question?",
        hashtags=["a", "b", "c", "d", "e"],
        stories=[long_story, _story(2), _story(3)],
    )
    caption = NewsAgent._build_caption(plan)
    # Leaves headroom for the ~5 hashtags appended at publish time.
    assert len(caption) <= 2010
    assert caption.endswith("…")


def test_caption_falls_back_to_summary_when_full_text_missing():
    # full_text is required by the model, but guard against an empty value.
    story = NewsStory(headline="H", summary="Fallback summary text.", insight="i", full_text="")
    plan = NewsCarouselPlan(
        lead_headline="Today in AI",
        caption="Intro.",
        closing_question="Q?",
        hashtags=["a", "b", "c", "d", "e"],
        stories=[story, _story(2), _story(3)],
    )
    caption = NewsAgent._build_caption(plan)
    assert "Fallback summary text." in caption
