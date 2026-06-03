"""Regenerate thumbnails for all scheduled posts using the new logo overlay.

Handles both standard posts (single thumbnail) and carousel posts (one image
per slide).  Fetches from Supabase, regenerates via Imagen with the corrected
small-corner logo, and updates the database.

Usage (from Railway Console or locally with credentials set):
    python -m scripts.regen_thumbnails

Options:
    --dry-run       Print which posts would be processed without calling Imagen.
    --limit N       Process at most N posts (default: all).
    --type standard Process only standard posts.
    --type carousel Process only carousel posts.
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def _regen_standard(sb, rows, agent, dry_run: bool) -> tuple[int, int]:
    from core.models import Post

    ok = fail = 0
    for r in rows:
        title = r.get("title") or r.get("topic", "Untitled")
        if dry_run:
            logger.info("  [dry-run] would regen: %s (%s)", title, r.get("platform"))
            continue
        post = Post(
            id=r["id"],
            pillar=r.get("pillar", ""),
            platform=r.get("platform", "instagram"),
            topic=r.get("topic", ""),
            title=r.get("title", ""),
        )
        try:
            logger.info("Regenerating: %s (%s)…", title, post.platform)
            raw_bytes = agent.generate_raw(post)
            final_bytes = agent.apply_overlay(raw_bytes)
            agent.upload(post, final_bytes)
            sb.table("posts").update({"thumbnail_url": post.thumbnail_url}).eq(
                "id", post.id
            ).execute()
            logger.info("  ✓ %s", post.thumbnail_url)
            ok += 1
        except Exception:
            logger.exception("  ✗ failed for post %s", r.get("id", "?")[:8])
            fail += 1
    return ok, fail


def _regen_carousels(
    sb, rows, carousel_agent, dry_run: bool, quality_agent=None
) -> tuple[int, int]:
    import uuid as _uuid

    from core.models import Post

    ok = fail = 0
    for r in rows:
        title = r.get("title") or r.get("topic", "Untitled")
        n_slides = len(r.get("slides") or [])
        if dry_run:
            logger.info(
                "  [dry-run] would regen carousel: %s (%s, %d slides)",
                title,
                r.get("platform"),
                n_slides,
            )
            continue
        source = Post(
            id=r["id"],
            pillar=r.get("pillar", ""),
            platform=r.get("platform", "instagram"),
            topic=r.get("topic", ""),
            title=r.get("title", ""),
            caption=r.get("caption", ""),
            hashtags=list(r.get("hashtags") or []),
        )
        try:
            logger.info(
                "Regenerating carousel: %s (%s, %d slides)…",
                title,
                source.platform,
                n_slides,
            )
            new_id = str(_uuid.uuid4())
            plan = carousel_agent._plan_carousel(source)
            slides = carousel_agent._generate_images(
                new_id, source, plan, quality_agent=quality_agent
            )
            thumbnail_url = slides[0]["image_url"] if slides else None
            sb.table("posts").update(
                {
                    "slides": slides,
                    "thumbnail_url": thumbnail_url,
                    "title": plan.cover_headline,
                }
            ).eq("id", r["id"]).execute()
            logger.info("  ✓ %d slides regenerated", len(slides))
            ok += 1
        except Exception:
            logger.exception("  ✗ failed for carousel %s", r.get("id", "?")[:8])
            fail += 1
    return ok, fail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--type",
        choices=["standard", "carousel", "all"],
        default="all",
        dest="post_type",
    )
    args = parser.parse_args()

    from supabase import create_client

    from core.config import config

    if not config.supabase_url or not config.supabase_key:
        logger.error("SUPABASE_URL / SUPABASE_KEY not set")
        return 1
    if not config.google_api_key:
        logger.error("GOOGLE_API_KEY not set — Imagen unavailable")
        return 1

    sb = create_client(config.supabase_url, config.supabase_key)

    do_standard = args.post_type in ("standard", "all")
    do_carousel = args.post_type in ("carousel", "all")

    std_rows = []
    car_rows = []

    if do_standard:
        std_rows = (
            sb.table("posts")
            .select("*")
            .eq("post_type", "standard")
            .eq("status", "scheduled")
            .execute()
            .data
            or []
        )
        if args.limit:
            std_rows = std_rows[: args.limit]

    if do_carousel:
        car_rows = (
            sb.table("posts")
            .select("*")
            .eq("post_type", "carousel")
            .eq("status", "scheduled")
            .execute()
            .data
            or []
        )
        if args.limit:
            car_rows = car_rows[: args.limit]

    total = len(std_rows) + len(car_rows)
    if total == 0:
        logger.info("No scheduled posts found — nothing to do.")
        return 0

    logger.info(
        "Found %d post(s) to refresh (%d standard, %d carousel).",
        total,
        len(std_rows),
        len(car_rows),
    )

    ok = fail = 0

    if std_rows:
        from agents.thumbnail_agent import ThumbnailAgent

        agent = ThumbnailAgent(config)
        s_ok, s_fail = _regen_standard(sb, std_rows, agent, args.dry_run)
        ok += s_ok
        fail += s_fail

    if car_rows:
        from agents.carousel_agent import CarouselAgent
        from agents.quality_agent import QualityAgent
        from core.config import ConfigError

        carousel_agent = CarouselAgent(config)
        try:
            quality_agent = QualityAgent(config)
        except ConfigError:
            quality_agent = None
            logger.warning("QualityAgent unavailable (no Anthropic key) — skipping per-slide QC")
        c_ok, c_fail = _regen_carousels(sb, car_rows, carousel_agent, args.dry_run, quality_agent)
        ok += c_ok
        fail += c_fail

    if args.dry_run:
        logger.info("Dry run complete — no changes made.")
    else:
        logger.info("Done — %d regenerated, %d failed.", ok, fail)

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
