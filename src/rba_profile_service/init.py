"""Create the profile schema and seed home profiles, once (C-4).

    python -m rba_profile_service.init

Runs as a Kubernetes Job before the consumer starts. Idempotent: tables via
`create_all`, profiles with `SET NX`, so a real history is never overwritten.
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from rba_profile_service.config import Settings, get_settings
from rba_profile_service.db import Base
from rba_profile_service.seed import seed_home_profile


def initialise(settings: Settings, engine: Engine | None = None) -> None:
    Base.metadata.create_all(engine or create_engine(settings.database_url, future=True))
    for user_id in settings.profile_user_ids():
        seed_home_profile(
            redis_url=settings.redis_url,
            key_prefix=settings.redis_key_prefix,
            user_id=user_id,
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    initialise(get_settings())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
