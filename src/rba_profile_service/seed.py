"""Seed a usual home ProfileState for the demo users (Demo-2).

Uses ``rba_features.update_profile`` so the Redis blob matches online scoring.
``SET NX`` so a live history is never overwritten.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import redis
from rba_features.features import update_profile
from rba_features.population import TOTAL_FIELD, population_fields
from rba_features.profile import ProfileState, profile_to_dict

logger = logging.getLogger(__name__)

HOME_IP = "203.0.113.10"
HOME_ASN = "7303"
HOME_COUNTRY = "AR"
# Roku Bank's Martín (ADR-0033 renamed the seeded users).
DEFAULT_USER_ID = "usr_rb_martin"

_COMBOS = (
    ("desktop", "macOS", "Chrome"),
    ("desktop", "Windows", "Chrome"),
    ("mobile", "Android", "Chrome"),
)


def home_events() -> list[dict]:
    """Two weeks of usual logins: AR / residential ASN / home TEST-NET."""
    base = datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)
    events = []
    for day in range(14):
        for hour in range(8, 22, 2):
            device, os_name, browser = _COMBOS[len(events) % len(_COMBOS)]
            events.append(
                {
                    "login_timestamp": base + timedelta(days=day, hours=hour - 8),
                    "ip_address": HOME_IP,
                    "asn": HOME_ASN,
                    "country": HOME_COUNTRY,
                    "device_type": device,
                    "os": os_name,
                    "browser": browser,
                    "login_successful": True,
                }
            )
    return events


def build_home_profile() -> ProfileState:
    """Enough history that a usual login can ALLOW."""
    profile = ProfileState()
    for event in home_events():
        update_profile(profile, event)
    return profile


def seed_home_profile(
    *,
    redis_url: str,
    key_prefix: str,
    user_id: str = DEFAULT_USER_ID,
    population_key: str | None = None,
) -> bool:
    """Return True if the key was written, False if it already existed.

    The seeded logins also count in the deployment's population (ADR-0042),
    as if they had been learned live.
    """
    client = redis.Redis.from_url(redis_url, decode_responses=True)
    key = f"{key_prefix}{user_id}"
    payload = json.dumps(profile_to_dict(build_home_profile()))
    wrote = bool(client.set(key, payload, nx=True))
    if wrote:
        if population_key:
            pipe = client.pipeline(transaction=False)
            for event in home_events():
                for field in [*population_fields(event), TOTAL_FIELD]:
                    pipe.hincrby(population_key, field, 1)
            pipe.execute()
        logger.info("seeded home profile key=%s", key)
    else:
        logger.info("home profile already present key=%s", key)
    return wrote
