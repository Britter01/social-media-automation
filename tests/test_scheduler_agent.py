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
