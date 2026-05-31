"""End-to-end smoke test — runs one post through the pipeline in dry-run.

    python -m scripts.smoke_test
    python -m scripts.smoke_test --pillar "Review" --platform linkedin --topic "earbuds"

What it does, stage by stage:
  1. Content  — runs the content agent if ANTHROPIC_API_KEY is set,
                otherwise injects a placeholder caption so the rest of the
                flow still exercises.
  2. Media    — runs the thumbnail agent if GOOGLE_API_KEY is set (best
                effort; failures are reported, not fatal).
  3. Schedule — always runs; picks the next optimal slot.
  4. Publish  — always runs with DRY_RUN forced on, so nothing is posted
                to any real platform.

It never touches Supabase, so you can run it with zero infrastructure.
Exit code is 0 on success, 1 if a non-skippable stage errors.
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys

from core.config import config, configure_logging
from core.models import Post, PostStatus

logger = logging.getLogger("scripts.smoke_test")


def _print_stage(label: str, post: Post) -> None:
    print(f"\n{'=' * 60}\n{label}  (status={post.status})\n{'-' * 60}")
    if post.title:
        print(f"title    : {post.title}")
    if post.caption:
        print(f"caption  : {post.caption}")
    if post.hashtags:
        print(f"hashtags : {' '.join('#' + h for h in post.hashtags)}")
    if post.thumbnail_url:
        print(f"thumbnail: {post.thumbnail_url}")
    if post.video_url:
        print(f"video    : {post.video_url}")
    if post.scheduled_time:
        print(f"scheduled: {post.scheduled_time.isoformat()}")
    if post.platform_post_id:
        print(f"post_id  : {post.platform_post_id}")
    if post.error:
        print(f"error    : {post.error}")


def run(pillar: str, platform: str, topic: str) -> int:
    configure_logging(config.log_level)

    # Force dry-run for this process so the publisher never posts for real.
    cfg = dataclasses.replace(config, dry_run=True)

    print(f"Smoke test for {cfg.brand_name} — dry-run, no posts will be published.")
    post = Post(pillar=pillar, platform=platform, topic=topic)
    _print_stage("0. Draft created", post)

    # --- 1. Content ------------------------------------------------------
    if cfg.anthropic_api_key:
        from agents.content_agent import ContentAgent

        try:
            ContentAgent(cfg).generate(post)
        except Exception:
            logger.exception("Content generation failed")
            return 1
    else:
        print("\n[skip] ANTHROPIC_API_KEY not set — using placeholder content.")
        post.title = f"{pillar}: a quick take"
        post.caption = (
            f"A placeholder caption for the {pillar} pillar on {platform}. "
            "Set ANTHROPIC_API_KEY to generate the real thing."
        )
        post.hashtags = ["britetechlifestyle", "tech", pillar.replace(" ", "").lower()]
        post.mark(PostStatus.CONTENT_READY)
    _print_stage("1. Content ready", post)

    # --- 2. Media (best effort) -----------------------------------------
    if cfg.google_api_key:
        from agents.thumbnail_agent import ThumbnailAgent

        try:
            ThumbnailAgent(cfg).generate(post)
        except Exception:
            logger.exception("Thumbnail generation failed (continuing)")
    else:
        print("\n[skip] GOOGLE_API_KEY not set — skipping thumbnail generation.")
    _print_stage("2. Media", post)

    # --- 3. Schedule -----------------------------------------------------
    from agents.scheduler_agent import SchedulerAgent

    SchedulerAgent(cfg).schedule(post)
    _print_stage("3. Scheduled", post)

    # --- 4. Publish (dry-run) -------------------------------------------
    from agents.publisher_agent import PublisherAgent

    try:
        PublisherAgent(cfg).publish(post)
    except Exception:
        logger.exception("Publish (dry-run) failed")
        return 1
    _print_stage("4. Published (dry-run)", post)

    print("\nSmoke test complete.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one post end-to-end in dry-run.")
    parser.add_argument("--pillar", default="AI Guide", help="Content pillar")
    parser.add_argument("--platform", default="instagram", help="Target platform")
    parser.add_argument("--topic", default="", help="Optional topic for the post")
    args = parser.parse_args()
    sys.exit(run(args.pillar, args.platform, args.topic))


if __name__ == "__main__":
    main()
