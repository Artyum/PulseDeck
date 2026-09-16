from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.perf_seed_lib import (
    DEFAULT_ENV,
    DEFAULT_PROJECT_NAME,
    TITLE_PREFIX,
    count_perf_tags,
    count_perf_tickets,
    count_perf_users,
    delete_perf_data,
    get_project,
    load_runtime_env,
    vacuum_db,
)

logger = logging.getLogger("pulsedeck.cleanup_performance")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Remove performance test data: tickets with a prefix in the "
            "Performance project and perf-seed-*@perf.pulsedeck.test users "
            "(only from that project)."
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
        "--prefix",
        default=TITLE_PREFIX,
        help="Ticket title prefix to remove",
    )
    parser.add_argument(
        "--keep-users",
        action="store_true",
        help="Remove tickets only, keep test users",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Run VACUUM ANALYZE after deletion (PostgreSQL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show counts without deleting",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion (required unless --dry-run)",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print(
            "Pass --yes to delete data or --dry-run to only check counts.",
            file=sys.stderr,
        )
        return 1

    load_runtime_env(args.env)

    from app.db.session import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    db = SessionLocal()
    try:
        project = get_project(db, args.project)
        if project is None:
            logger.info("Project %r not found — nothing to remove.", args.project)
            return 0
        ticket_count = count_perf_tickets(db, project.id, args.prefix)
        user_count = count_perf_users(db, project.id)
        tag_count = count_perf_tags(db, project.id)

        logger.info(
            "Project %r: %d tickets (prefix %r), %d test users, %d perf- tags",
            args.project,
            ticket_count,
            args.prefix,
            user_count,
            tag_count,
        )

        if args.dry_run:
            return 0

        tickets_removed, users_removed, tags_removed = delete_perf_data(
            db,
            project.id,
            args.prefix,
            delete_users=not args.keep_users,
        )
        logger.info(
            "Removed %d tickets, %d test users, %d tags",
            tickets_removed,
            users_removed,
            tags_removed,
        )

        if args.vacuum:
            vacuum_db(db)

        return 0
    except Exception:
        db.rollback()
        logger.exception("Cleanup failed")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
