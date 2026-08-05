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
            "Usuwa dane testów wydajnościowych: wątki z prefiksem w projekcie "
            "Performance i userzy perf-seed-*@perf.pulsedeck.test (tylko z tego projektu)."
        )
    )
    parser.add_argument(
        "--env",
        default=str(DEFAULT_ENV),
        help="Ścieżka do pliku .env (domyślnie deploy/.env.dev)",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT_NAME,
        help="Nazwa projektu (domyślnie Performance)",
    )
    parser.add_argument(
        "--prefix",
        default=TITLE_PREFIX,
        help="Prefiks tytułów wątków do usunięcia",
    )
    parser.add_argument(
        "--keep-users",
        action="store_true",
        help="Usuń tylko wątki, zostaw userów testowych",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="Po usunięciu uruchom VACUUM ANALYZE (PostgreSQL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pokaż liczniki bez usuwania",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Potwierdź usuwanie (wymagane poza --dry-run)",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.yes:
        print(
            "Podaj --yes aby usunąć dane lub --dry-run aby tylko sprawdzić liczniki.",
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
            logger.info("Brak projektu %r — nic do usunięcia.", args.project)
            return 0
        ticket_count = count_perf_tickets(db, project.id, args.prefix)
        user_count = count_perf_users(db, project.id)
        tag_count = count_perf_tags(db, project.id)

        logger.info(
            "Projekt %r: %d wątków (prefiks %r), %d userów testowych, %d tagów perf-",
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
            "Usunięto %d wątków, %d userów testowych, %d tagów",
            tickets_removed,
            users_removed,
            tags_removed,
        )

        if args.vacuum:
            vacuum_db(db)

        return 0
    except Exception:
        db.rollback()
        logger.exception("Cleanup nie powiódł się")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
