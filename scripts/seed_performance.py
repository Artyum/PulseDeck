from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.perf_seed_lib import (
    DEFAULT_ENV,
    DEFAULT_PROJECT_KEY,
    DEFAULT_PROJECT_NAME,
    TITLE_PREFIX,
    delete_perf_data,
    ensure_perf_staff,
    ensure_perf_tags,
    ensure_perf_users,
    ensure_project,
    load_runtime_env,
    log_db_target,
    pick_assignee,
    pick_author,
    pick_ticket_priority,
    pick_ticket_status,
    pick_ticket_tags,
    pick_ticket_type,
    plan_conversation_roles,
    project_feed_url,
    resolve_viewers,
)

logger = logging.getLogger("pulsedeck.seed_performance")


def sample_content_length(
    rng: random.Random,
    *,
    kind: str,
    min_len: int,
    max_len: int,
) -> int:
    def clamp(lo: int, hi: int) -> int:
        lo = max(min_len, lo)
        hi = min(max_len, hi)
        if lo > hi:
            return min(max(min_len, (lo + hi) // 2), max_len)
        return rng.randint(lo, hi)

    r = rng.random()
    if kind == "comment":
        if r < 0.90:
            return clamp(200, 800)
        if r < 0.99:
            return clamp(900, 2200)
        return clamp(3500, 5500)
    if r < 0.30:
        return clamp(200, 700)
    if r < 0.65:
        return clamp(700, 2000)
    if r < 0.90:
        return clamp(2000, 4500)
    return clamp(4500, 8000)


def sample_comment_count(rng: random.Random, *, max_comments: int) -> int:
    if max_comments <= 0:
        return 0

    def clamp(lo: int, hi: int) -> int:
        lo = max(1, lo)
        hi = min(max_comments, hi)
        if lo > hi:
            return min(max(1, lo), max_comments)
        return rng.randint(lo, hi)

    r = rng.random()
    if r < 0.18:
        return clamp(1, 1)
    if r < 0.42:
        return clamp(2, 3)
    if r < 0.70:
        return clamp(4, 7)
    if r < 0.88:
        return clamp(8, 14)
    if r < 0.97:
        return clamp(15, 25)
    return clamp(26, min(50, max_comments))


def markdown_message(
    fake, min_len: int, max_len: int, rng: random.Random | None = None
) -> str:
    rng = rng or random.Random()
    target = rng.randint(min_len, max_len)
    generators = [
        lambda: f"**{fake.sentence()}**",
        lambda: f"*{fake.sentence()}*",
        lambda: fake.paragraph(),
        lambda: "\n".join(f"- {fake.sentence()}" for _ in range(rng.randint(2, 7))),
        lambda: "\n".join(
            f"{i}. {fake.sentence()}" for i in range(1, rng.randint(3, 6))
        ),
        lambda: f"> {fake.paragraph(nb_sentences=2)}",
        lambda: f"`{fake.word()}` — {fake.sentence()}",
        lambda: f"[{fake.word()}](https://example.com/{fake.slug()})",
        lambda: f"**{fake.word()}**: {fake.paragraph()}",
    ]
    blocks: list[str] = []
    total = 0
    while total < target:
        block = rng.choice(generators)()
        blocks.append(block)
        total = len("\n\n".join(blocks))
    text = "\n\n".join(blocks)
    if len(text) > max_len:
        text = text[:max_len].rstrip()
    if len(text) < min_len:
        pad = fake.text(max_nb_chars=min_len - len(text) + 8).strip()
        text = f"{text}\n\n{pad}".strip()[:max_len]
    return text


def _content(fake, rng: random.Random, *, kind: str, min_len: int, max_len: int) -> str:
    n = sample_content_length(rng, kind=kind, min_len=min_len, max_len=max_len)
    return markdown_message(fake, n, n, rng=rng)


def seed(
    db,
    *,
    project,
    client_users: list,
    staff_users: list,
    viewers: list,
    tag_pool: list,
    tickets: int,
    max_comments: int,
    min_len: int,
    max_len: int,
    batch_size: int,
    prefix: str,
    locale: str,
    seed: int | None,
) -> tuple[int, int]:
    from faker import Faker
    from sqlalchemy import func, select

    from app.models.enums import TicketStatus
    from app.models.ticket import Comment, Ticket, TicketTag
    from app.models.user import Project
    from app.validation import clean

    fake = Faker(locale)
    rng = random.Random(seed)
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)

    project = db.scalar(
        select(Project).where(Project.id == project.id).with_for_update()
    )
    base_number = (
        db.scalar(
            select(func.coalesce(func.max(Ticket.number), 0)).where(
                Ticket.project_id == project.id
            )
        )
        or 0
    )

    ticket_count = 0
    comment_count = 0
    pending_tickets = 0
    clock = datetime.now(timezone.utc) - timedelta(
        milliseconds=tickets * (1 + max(max_comments, 0))
    )

    for seq in range(1, tickets + 1):
        author = pick_author(client_users)
        assignee = None if rng.random() < 0.05 else pick_assignee(viewers, seq)
        title = clean("ticket.title", f"{prefix} {seq}", lang="pl")
        description = clean(
            "ticket.description",
            _content(fake, rng, kind="description", min_len=min_len, max_len=max_len),
            lang="pl",
        )
        status = pick_ticket_status(rng)
        clock += timedelta(milliseconds=1)
        ticket_ts = clock
        ticket = Ticket(
            project_id=project.id,
            number=base_number + seq,
            author_id=author.id,
            assignee_id=assignee.id if assignee else None,
            title=title,
            description=description,
            type=pick_ticket_type(rng),
            status=status,
            priority=pick_ticket_priority(rng),
            closed_at=ticket_ts if status == TicketStatus.DONE else None,
            created_at=ticket_ts,
            updated_at=ticket_ts,
        )
        db.add(ticket)
        db.flush()

        for tag in pick_ticket_tags(tag_pool, rng):
            db.add(TicketTag(ticket_id=ticket.id, tag_id=tag.id))

        role_plan = plan_conversation_roles(
            sample_comment_count(rng, max_comments=max_comments), rng
        )
        for is_staff in role_plan:
            pool = staff_users if is_staff else client_users
            comment_author = pick_author(pool)
            content = clean(
                "comment.content",
                _content(fake, rng, kind="comment", min_len=min_len, max_len=max_len),
                lang="pl",
            )
            clock += timedelta(milliseconds=1)
            db.add(
                Comment(
                    ticket_id=ticket.id,
                    author_id=comment_author.id,
                    content=content,
                    is_internal=False,
                    created_at=clock,
                )
            )
            comment_count += 1

        if role_plan:
            ticket.updated_at = clock
            if status == TicketStatus.DONE:
                ticket.closed_at = clock

        ticket_count += 1
        pending_tickets += 1

        if pending_tickets >= batch_size:
            db.commit()
            logger.info("Saved %d / %d tickets", ticket_count, tickets)
            pending_tickets = 0

    if pending_tickets:
        db.commit()

    return ticket_count, comment_count


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Seed performance data — tickets and comments (markdown + Faker). "
            "Each run appends new tickets (numbered from MAX+1). "
            "Use cleanup_performance.py or --cleanup to remove test data."
        )
    )
    parser.add_argument(
        "--env",
        default=str(DEFAULT_ENV),
        help="Path to .env file (default: deploy/.env.dev)",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT_NAME,
        help="Project name (default: Performance)",
    )
    parser.add_argument(
        "--project-key",
        default=DEFAULT_PROJECT_KEY,
        help="Project key when auto-creating (default: PERF)",
    )
    parser.add_argument("--tickets", type=int, default=1000, help="Number of tickets")
    parser.add_argument(
        "--comments",
        type=int,
        default=30,
        help="Max comments per ticket (random count from 1…N)",
    )
    parser.add_argument(
        "--users",
        type=int,
        default=10,
        help="Number of test clients (perf-seed-NNN@perf.pulsedeck.test)",
    )
    parser.add_argument(
        "--staff",
        type=int,
        default=3,
        help="Number of test staff (perf-seed-staff-NNN@perf.pulsedeck.test)",
    )
    parser.add_argument(
        "--tag-pool",
        type=int,
        default=25,
        help="Number of tags in the pool (perf-NNN); 0–5 random per ticket",
    )
    parser.add_argument(
        "--min-len",
        type=int,
        default=10,
        help="Minimum content length (comments/descriptions distribution)",
    )
    parser.add_argument(
        "--max-len",
        type=int,
        default=8000,
        help="Maximum content length (comments/descriptions distribution)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=50,
        help="Commit every N tickets",
    )
    parser.add_argument(
        "--prefix",
        default=TITLE_PREFIX,
        help="Ticket title prefix (for cleanup)",
    )
    parser.add_argument(
        "--locale", default="pl_PL", help="Faker locale (e.g. pl_PL, en_US)"
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="RNG seed (reproducible data)"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove test data (tickets + perf users) before seeding",
    )
    args = parser.parse_args()

    if args.min_len < 1 or args.max_len < args.min_len:
        print("Invalid comment length range.", file=sys.stderr)
        return 1
    if args.tickets < 1 or args.comments < 0:
        print("tickets >= 1, comments >= 0", file=sys.stderr)
        return 1
    if args.users < 1:
        print("users >= 1", file=sys.stderr)
        return 1
    if args.staff < 1:
        print("staff >= 1", file=sys.stderr)
        return 1
    if args.tag_pool < 1:
        print("tag-pool >= 1", file=sys.stderr)
        return 1

    load_runtime_env(args.env)
    log_db_target()

    from app.db.session import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db = SessionLocal()
    started = time.perf_counter()
    try:
        project = ensure_project(
            db,
            name=args.project,
            key=args.project_key,
        )

        if args.cleanup:
            tickets_removed, users_removed, tags_removed = delete_perf_data(
                db, project.id, args.prefix, delete_users=True
            )
            logger.info(
                "Cleanup: removed %d tickets, %d users, %d tags",
                tickets_removed,
                users_removed,
                tags_removed,
            )

        client_users = ensure_perf_users(
            db,
            project.id,
            args.users,
            locale=args.locale,
            seed=args.seed,
        )
        staff_users = ensure_perf_staff(
            db,
            project.id,
            args.staff,
            locale=args.locale,
            seed=args.seed,
        )
        tag_pool = ensure_perf_tags(db, project.id, args.tag_pool)
        viewers = resolve_viewers(db, project.id)
        db.commit()
        logger.info(
            "Clients: %d, seeded staff: %d, tags: %d, assigned staff/admin: %d",
            len(client_users),
            len(staff_users),
            len(tag_pool),
            len(viewers),
        )

        logger.info(
            "Seed: project=%r (key=%s), tickets=%d, max comments/ticket=%d, length %d–%d",
            args.project,
            project.key,
            args.tickets,
            args.comments,
            args.min_len,
            args.max_len,
        )
        ticket_count, comment_count = seed(
            db,
            project=project,
            client_users=client_users,
            staff_users=staff_users,
            viewers=viewers,
            tag_pool=tag_pool,
            tickets=args.tickets,
            max_comments=args.comments,
            min_len=args.min_len,
            max_len=args.max_len,
            batch_size=max(1, args.batch),
            prefix=args.prefix,
            locale=args.locale,
            seed=args.seed,
        )
        elapsed = time.perf_counter() - started
        logger.info(
            "Done: %d tickets, %d comments in %.1f s",
            ticket_count,
            comment_count,
            elapsed,
        )
        logger.info("Feed (default view): %s", project_feed_url(project.key))
        return 0
    except Exception:
        db.rollback()
        logger.exception("Seed failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
