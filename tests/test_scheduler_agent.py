"""Tests for agents.scheduler_agent."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.scheduler_agent import SchedulerAgent
from core.models import Post, PostStatus


def test_next_slot_is_in_the_future(base_config):
    agent = SchedulerAgent(base_config)
    tz = ZoneInfo(base_config.timezone)
    after = datetime(2026, 6, 1, 0, 0, tzinfo=tz)  # Monday 00:00
    slot = agent.next_slot("instagram", after=after)
    assert slot > after


def test_linkedin_slot_falls_on_tue_to_thu(base_config):
    agent = SchedulerAgent(base_config)
    tz = ZoneInfo(base_config.timezone)
    # Start on a Friday; LinkedIn's table only has Tue/Wed/Thu slots.
    after = datetime(2026, 6, 5, 12, 0, tzinfo=tz)  # Friday
    slot = agent.next_slot("linkedin", after=after)
    assert slot.weekday() in {1, 2, 3}
    assert slot > after


def test_unknown_platform_uses_default_slot(base_config):
    agent = SchedulerAgent(base_config)
    slot = agent.next_slot("myspace")
    assert isinstance(slot, datetime)


def test_schedule_sets_status_and_time(base_config):
    agent = SchedulerAgent(base_config)
    post = Post(pillar="Review", platform="tiktok")
    agent.schedule(post)
    assert post.status == PostStatus.SCHEDULED.value
    assert post.scheduled_time is not None


def test_chained_scheduling_caps_posts_per_day_per_platform(base_config):
    # This is the guarantee behind the Rebalance button and the recovery-path
    # fix: when each post is scheduled after the previous one for the platform,
    # a single calendar day never gets more than that platform's slot count.
    agent = SchedulerAgent(base_config)
    tz = ZoneInfo(base_config.timezone)
    after = datetime(2026, 6, 1, 0, 0, tzinfo=tz)

    for platform, max_per_day in (("instagram", 2), ("facebook", 2), ("twitter", 3)):
        per_day: dict = {}
        last = after
        for _ in range(20):  # schedule 20 posts back-to-back for this platform
            slot = agent.next_slot(platform, after=last)
            assert slot > last  # strictly chained forward
            per_day[slot.date()] = per_day.get(slot.date(), 0) + 1
            last = slot
        assert max(per_day.values()) <= max_per_day, (
            f"{platform}: {max(per_day.values())} on one day exceeds {max_per_day}"
        )
