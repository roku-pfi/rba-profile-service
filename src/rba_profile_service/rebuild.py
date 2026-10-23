"""Rebuild every profile and the population from the learned history (ADR-0043).

freeman-0.4.0 reads per-prefix counts that profiles written before it lack, so
to it every existing user would look new. `profile_history` holds every login a
profile ever learned (and every failure it counted), in order, so replaying it
through today's `update_profile` gives the profile the user would have had.
Seeded home histories (local only) are replayed first, as at startup.

    python -m rba_profile_service.rebuild
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict

import redis
from rba_contracts import LoginEventSnapshot
from rba_features.features import update_profile
from rba_features.population import learn_population
from rba_features.profile import ProfileState, profile_to_dict
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from rba_profile_service.config import Settings, get_settings
from rba_profile_service.db import ProfileHistoryRow
from rba_profile_service.seed import home_events

logger = logging.getLogger(__name__)


def rebuild(settings: Settings) -> dict[str, int]:
    engine = create_engine(settings.database_url, future=True)
    with sessionmaker(bind=engine, future=True)() as session:
        rows = list(session.scalars(select(ProfileHistoryRow).order_by(ProfileHistoryRow.occurred_at, ProfileHistoryRow.id)))
    history: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        history[row.user_id].append(LoginEventSnapshot.model_validate(row.login).to_feature_event())

    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    client.delete(settings.redis_population_key)

    def hincrby(field: str, n: int) -> int:
        return client.hincrby(settings.redis_population_key, field, n)

    seeded = set(settings.profile_user_ids())
    counts = {}
    for user_id in sorted(seeded | set(history)):
        events = (home_events() if user_id in seeded else []) + history.get(user_id, [])
        profile = ProfileState()
        for event in events:
            update_profile(profile, event)
            if event.get("login_successful") is not False:
                learn_population(event, hincrby)
        client.set(f"{settings.redis_key_prefix}{user_id}", json.dumps(profile_to_dict(profile)))
        counts[user_id] = profile.login_count
        logger.info("rebuilt user_id=%s logins=%s", user_id, profile.login_count)
    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    counts = rebuild(get_settings())
    print(f"rebuilt {len(counts)} profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
