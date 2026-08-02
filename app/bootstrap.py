from __future__ import annotations

import logging
import sys

from app.db.session import SessionLocal
from app.logging_setup import setup_logging
from app.services.auth import ensure_admin_seed

logger = logging.getLogger("pulsedeck.bootstrap")


def main() -> int:
    setup_logging()
    db = SessionLocal()
    try:
        ensure_admin_seed(db)
    except Exception:
        logger.exception("Bootstrap failed")
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
