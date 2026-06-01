"""Review researched topics before they become posts.

The human approval gate. The research agent stores trending topics it
finds as ``selected`` (awaiting review); this tool lets you see them and
approve or reject each. Approved topics are picked up by the worker's
approved-topic pipeline (or ``ResearchAgent.generate_for_approved``) and
turned into scheduled posts. Rejected ones are dropped.

    # List everything awaiting review
    python -m scripts.review_topics

    # Approve / reject by id (a unique id prefix is enough)
    python -m scripts.review_topics --approve 1a2b 9f3c
    python -m scripts.review_topics --reject 4d5e
    python -m scripts.review_topics --approve-all

    # Review one at a time, interactively
    python -m scripts.review_topics --interactive

Requires Supabase to be configured (SUPABASE_URL / SUPABASE_KEY).
"""

from __future__ import annotations

import argparse
import sys

from core.config import config, configure_logging
from core.models import Topic, TopicStatus


def pending_topics(db) -> list[Topic]:
    """Topics awaiting review, highest-scoring first."""
    return db.topics_by_status(TopicStatus.PENDING_APPROVAL)


def _resolve(pending: list[Topic], token: str) -> Topic | None:
    """Find a pending topic by exact id or a unique id prefix."""
    matches = [t for t in pending if t.id == token or t.id.startswith(token)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        print(f"[skip] no pending topic matches {token!r}")
    else:
        print(f"[skip] {token!r} is ambiguous — matches {len(matches)} topics; use a longer id")
    return None


def set_status(db, tokens: list[str], status: TopicStatus) -> list[Topic]:
    """Transition the matching pending topics to ``status`` and persist."""
    pending = pending_topics(db)
    changed: list[Topic] = []
    for token in tokens:
        topic = _resolve(pending, token)
        if topic is None:
            continue
        topic.mark(status)
        db.upsert_topic(topic)
        changed.append(topic)
        print(f"[{status.value}] {topic.id[:8]}  {topic.title}")
    return changed


def _print_topics(topics: list[Topic]) -> None:
    if not topics:
        print("No topics awaiting review.")
        return
    print(f"\n{len(topics)} topic(s) awaiting review:\n")
    for t in topics:
        print(f"  {t.id[:8]}  [{t.relevance_score:>3}]  {t.pillar} -> {t.platform}")
        print(f"          {t.title}")
        if t.content_angle:
            print(f"          angle: {t.content_angle}")
        if t.rationale:
            print(f"          why:   {t.rationale}")
        for url in t.sources:
            print(f"          src:   {url}")
        print()


def _interactive(db) -> None:
    """Walk pending topics one at a time, prompting for a decision."""
    pending = pending_topics(db)
    if not pending:
        print("No topics awaiting review.")
        return
    for t in pending:
        _print_topics([t])
        choice = input("    [a]pprove / [r]eject / [s]kip / [q]uit? ").strip().lower()
        if choice in {"q", "quit"}:
            break
        if choice in {"a", "approve"}:
            set_status(db, [t.id], TopicStatus.APPROVED)
        elif choice in {"r", "reject"}:
            set_status(db, [t.id], TopicStatus.REJECTED)
        else:
            print("    skipped")


def run(args: argparse.Namespace) -> int:
    configure_logging(config.log_level)
    try:
        from core.database import get_database

        db = get_database()
    except Exception as exc:  # noqa: BLE001 - surface a clear setup message
        print(f"Could not connect to Supabase: {exc}", file=sys.stderr)
        print("Set SUPABASE_URL and SUPABASE_KEY in your environment / .env.", file=sys.stderr)
        return 1

    if args.interactive:
        _interactive(db)
        return 0

    if args.approve_all:
        set_status(db, [t.id for t in pending_topics(db)], TopicStatus.APPROVED)
        return 0

    if args.approve:
        set_status(db, args.approve, TopicStatus.APPROVED)
    if args.reject:
        set_status(db, args.reject, TopicStatus.REJECTED)

    if not (args.approve or args.reject):
        _print_topics(pending_topics(db))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Review researched topics before they post.")
    parser.add_argument("--approve", nargs="+", metavar="ID", help="Approve topics by id (prefix)")
    parser.add_argument("--reject", nargs="+", metavar="ID", help="Reject topics by id (prefix)")
    parser.add_argument("--approve-all", action="store_true", help="Approve every pending topic")
    parser.add_argument("--interactive", action="store_true", help="Review topics one at a time")
    sys.exit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
