"""Tests for scripts.review_topics (Supabase mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

from core.models import Topic, TopicStatus
from scripts.review_topics import pending_topics, set_status


def _pending():
    return [
        Topic(id="aaaa1111", title="A", pillar="Review", platform="instagram", relevance_score=90),
        Topic(id="bbbb2222", title="B", pillar="AI Guide", platform="twitter", relevance_score=80),
    ]


def _db(pending=None):
    db = MagicMock()
    db.topics_by_status.return_value = pending if pending is not None else _pending()
    return db


def test_pending_topics_queries_selected():
    db = _db()
    pending_topics(db)
    db.topics_by_status.assert_called_once_with(TopicStatus.SELECTED)


def test_approve_by_full_id_marks_and_persists():
    db = _db()
    changed = set_status(db, ["aaaa1111"], TopicStatus.APPROVED)
    assert len(changed) == 1
    assert changed[0].status == TopicStatus.APPROVED.value
    db.upsert_topic.assert_called_once()


def test_approve_by_unique_prefix():
    db = _db()
    changed = set_status(db, ["bbbb"], TopicStatus.APPROVED)
    assert [t.id for t in changed] == ["bbbb2222"]


def test_reject_sets_rejected_status():
    db = _db()
    changed = set_status(db, ["aaaa1111"], TopicStatus.REJECTED)
    assert changed[0].status == TopicStatus.REJECTED.value


def test_unknown_id_is_skipped():
    db = _db()
    changed = set_status(db, ["zzzz9999"], TopicStatus.APPROVED)
    assert changed == []
    db.upsert_topic.assert_not_called()


def test_ambiguous_prefix_is_skipped():
    pending = [
        Topic(id="abc111", title="A", pillar="Review", platform="instagram"),
        Topic(id="abc222", title="B", pillar="Review", platform="instagram"),
    ]
    db = _db(pending)
    changed = set_status(db, ["abc"], TopicStatus.APPROVED)
    assert changed == []  # 'abc' matches both → ambiguous, skipped
    db.upsert_topic.assert_not_called()
