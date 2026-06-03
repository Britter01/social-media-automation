"""Regenerate thumbnails for all scheduled posts using the new logo overlay.

Fetches every scheduled standard post, generates a fresh Imagen image with the
correct small-corner logo, uploads it to Supabase, and updates the thumbnail_url.

Usage (from Railway "Execute command" or locally with credentials set):
    python -m scripts.regen_thumbnails

Options:
    --dry-run    Print which posts would be processed without calling Imagen.
    --limit N    Process at most N posts (default: all).
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    from supabase import create_client

    from agents.thumbnail_agent import ThumbnailAgent
    from core.config import config
    from core.models import Post

    if not config.supabase_url or not config.supabase_key:
        logger.error("SUPABASE_URL / SUPABASE_KEY not set")
        return 1
    if not config.google_api_key:
        logger.error("GOOGLE_API_KEY not set — Imagen unavailable")
        return 1

    sb = create_client(config.supabase_url, config.supabase_key)

    rows = (
        sb.table("posts")
        .select("*")
        .eq("post_type", "standard")
        .eq("status", "scheduled")
        .execute()
        .data
        or []
    )

    if args.limit:
        rows = rows[: args.limit]

    if not rows:
        logger.info("No scheduled standard posts found — nothing to do.")
        return 0

    logger.info("Found %d scheduled post(s) to refresh.", len(rows))

    if args.dry_run:
        for r in rows:
            title = r.get("title") or r.get("topic", "Untitled")
            logger.info("  [dry-run] would regen: %s (%s)", title, r.get("platform"))
        return 0

    agent = ThumbnailAgent(config)
    ok = 0
    fail = 0

    for r in rows:
        title = r.get("title") or r.get("topic", "Untitled")
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
            logger.info("  ✓ uploaded → %s", post.thumbnail_url)
            ok += 1
        except Exception:
            logger.exception("  ✗ failed for post %s", r.get("id", "?")[:8])
            fail += 1

    logger.info("Done — %d regenerated, %d failed.", ok, fail)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
