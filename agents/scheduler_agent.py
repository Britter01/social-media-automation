"""Scheduler agent — picks optimal posting times per platform.

Given a post and a "from" time, returns the next high-engagement slot for
that platform in the brand's timezone. Slots are drawn from widely-cited
best-time-to-post windows per network; tune the tables to your own
analytics as you gather data.

The agent is deterministic and side-effect free — it only computes a
``datetime``. Persisting the schedule is the caller's job.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.config import Config, config
from core.models import Post, PostStatus

logger = logging.getLogger(__name__)

# Best-time windows as (weekday set, hour, minute), local to the brand TZ.
# weekday: Monday=0 .. Sunday=6. These are sensible defaults, not gospel —
# replace with your own engagement data over time.
_OPTIMAL_SLOTS: dict[str, list[tuple]] = {
    "instagram": [
        ({0, 1, 2, 3, 4}, 11, 0),  # weekday late morning
        ({0, 1, 2, 3, 4}, 19, 0),  # weekday evening
        ({5, 6}, 10, 0),  # weekend mid-morning
    ],
    "twitter": [
        ({0, 1, 2, 3, 4}, 9, 0),  # weekday commute
        ({0, 1, 2, 3, 4}, 12, 0),  # weekday lunch
        ({0, 1, 2, 3, 4}, 17, 0),  # weekday wind-down
    ],
    "linkedin": [
        ({1, 2, 3}, 8, 0),  # Tue-Thu before work
        ({1, 2, 3}, 12, 0),  # Tue-Thu lunch
        ({1, 2, 3}, 17, 30),  # Tue-Thu end of day
    ],
    "youtube": [
        ({4, 5}, 15, 0),  # Fri/Sat afternoon
        ({5, 6}, 11, 0),  # weekend late morning
    ],
    "tiktok": [
        ({1, 3, 4}, 18, 0),  # Tue/Thu/Fri evening
        ({0, 1, 2, 3, 4}, 20, 0),  # weekday prime time
        ({5, 6}, 12, 0),  # weekend midday
    ],
}

# Fallback if a platform has no table entry.
_DEFAULT_SLOTS = [({0, 1, 2, 3, 4}, 12, 0)]


class SchedulerAgent:
    """Computes the next optimal posting time for a post."""

    def __init__(self, cfg: Config = config) -> None:
        self._cfg = cfg
        self._tz = ZoneInfo(cfg.timezone)

    def next_slot(self, platform: str, after: datetime | None = None) -> datetime:
        """Return the next optimal posting time strictly after ``after``.

        Searches forward day by day (up to two weeks) for the earliest
        slot whose weekday and time fall after the reference time.
        """
        reference = (after or datetime.now(self._tz)).astimezone(self._tz)
        slots = _OPTIMAL_SLOTS.get(platform, _DEFAULT_SLOTS)

        best: datetime | None = None
        for day_offset in range(0, 14):
            day = reference + timedelta(days=day_offset)
            for weekdays, hour, minute in slots:
                if day.weekday() not in weekdays:
                    continue
                candidate = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if candidate <= reference:
                    continue
                if best is None or candidate < best:
                    best = candidate
            if best is not None:
                break

        # Defensive fallback: one hour out if the tables somehow miss.
        if best is None:
            best = reference + timedelta(hours=1)

        logger.debug("Next %s slot after %s -> %s", platform, reference, best)
        return best

    def schedule(self, post: Post, after: datetime | None = None) -> Post:
        """Assign ``post.scheduled_time`` and mark it scheduled, in place."""
        post.scheduled_time = self.next_slot(post.platform, after)
        post.mark(PostStatus.SCHEDULED)
        logger.info(
            "Scheduled post %s for %s at %s",
            post.id,
            post.platform,
            post.scheduled_time.isoformat(),
        )
        return post
