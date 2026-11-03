"""Rebuild every profile and each tenant's population from the learned history (ADR-0043, ADR-0046).

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
from rba_features.population import TOTAL_FIELD, learn_population, population_key
from rba_features.profile import ProfileState, profile_to_dict
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from rba_profile_service.config import Settings, get_settings
from rba_profile_service.db import ProfileHistoryRow
from rba_profile_service.seed import home_events

logger = logging.getLogger(__name__)


def rebuild(settings: Settings) -> dict[str, int]:
    """Replay the history one user at a time, streamed from Postgres.

    Load tests leave ~10⁵ rows; holding them all, or one Valkey round trip
    per counter, does not fit a 128 MiB pod. Each tenant's population is
    counted in memory and written once, one HSET per tenant.
    """
    engine = create_engine(settings.database_url, future=True)
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    base = settings.redis_population_key
    seeded = dict((user_id, tenant_id) for tenant_id, user_id in settings.profile_seeds())
    populations: dict[str, dict[str, int]] = defaultdict(dict)
    counts: dict[str, int] = {}

    def replay(user_id: str, tenant_id: str, history: list[dict]) -> None:
        population = populations[tenant_id]

        def hincrby(field: str, n: int) -> int:
            population[field] = population.get(field, 0) + n
            return population[field]

        events = (home_events() if user_id in seeded else []) + history
        profile = ProfileState()
        for event in events:
            update_profile(profile, event)
            if event.get("login_successful") is not False:
                learn_population(event, hincrby)
        client.set(f"{settings.redis_key_prefix}{user_id}", json.dumps(profile_to_dict(profile)))
        counts[user_id] = profile.login_count

    query = (
        select(ProfileHistoryRow.user_id, ProfileHistoryRow.tenant_id, ProfileHistoryRow.login)
        .order_by(ProfileHistoryRow.user_id, ProfileHistoryRow.occurred_at, ProfileHistoryRow.id)
        .execution_options(yield_per=1000)
    )
    with sessionmaker(bind=engine, future=True)() as session:
        current: tuple[str, str] | None = None
        history: list[dict] = []
        for user_id, tenant_id, login in session.execute(query):
            if current is not None and current[0] != user_id:
                replay(*current, history)
                history = []
            current = (user_id, tenant_id)
            history.append(LoginEventSnapshot.model_validate(login).to_feature_event())
        if current is not None:
            replay(*current, history)
    for user_id, tenant_id in seeded.items():
        if user_id not in counts:
            replay(user_id, tenant_id, [])

    # The tenants' hashes, and the single deployment-wide one ADR-0046 replaced.
    client.delete(base, *client.scan_iter(match=population_key(base, "*")))
    for tenant_id, population in populations.items():
        if population:
            client.hset(population_key(base, tenant_id), mapping=population)
    logger.info("rebuilt %s profiles; populations: %s", len(counts),
                {t: p.get(TOTAL_FIELD, 0) for t, p in populations.items()})
    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    counts = rebuild(get_settings())
    print(f"rebuilt {len(counts)} profiles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
