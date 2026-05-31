"""Tests for the cron orchestration helpers."""

from __future__ import annotations

from scheduler.cron import _round_robin_platforms


def test_round_robin_pairs_each_pillar_with_a_platform():
    pillars = ["A", "B", "C"]
    platforms = ["x", "y"]
    pairs = _round_robin_platforms(pillars, platforms)
    assert pairs == [("A", "x"), ("B", "y"), ("C", "x")]


def test_round_robin_empty_platforms():
    assert _round_robin_platforms(["A"], []) == []
