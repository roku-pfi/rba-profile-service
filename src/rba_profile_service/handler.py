"""Apply DecisionMadeEvent to Redis ProfileState (idempotent)."""

from __future__ import annotations

import json
import logging
from copy import deepcopy

import redis
from rba_contracts import DecisionMadeEvent
from rba_features.features import update_profile
from rba_features.profile import profile_from_dict, profile_to_dict
from sqlalchemy.orm import Session, sessionmaker

from rba_profile_service.db import ProcessedEvent, ProfileHistoryRow, already_processed

logger = logging.getLogger(__name__)


class ProfileUpdater:
    def __init__(
        self,
        *,
        redis_url: str,
        key_prefix: str,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix
        self._sessions = session_factory

    def _key(self, user_id: str) -> str:
        return f"{self._prefix}{user_id}"

    def handle(self, event: DecisionMadeEvent) -> bool:
        """Return True if applied, False if duplicate / skipped."""
        with self._sessions() as session:
            if already_processed(session, event.event_id):
                logger.info("skip duplicate event_id=%s", event.event_id)
                return False

            if event.login is None:
                logger.warning(
                    "event_id=%s missing login snapshot — cannot update profile",
                    event.event_id,
                )
                # Still mark processed so we do not retry forever without a login payload.
                session.add(ProcessedEvent(event_id=event.event_id))
                session.commit()
                return False

            raw = self._redis.get(self._key(event.user_id))
            profile = profile_from_dict(json.loads(raw) if raw else None)
            updated = update_profile(deepcopy(profile), event.login.to_feature_event())
            self._redis.set(self._key(event.user_id), json.dumps(profile_to_dict(updated)))

            session.add(
                ProfileHistoryRow(
                    event_id=event.event_id,
                    user_id=event.user_id,
                    application_id=event.application_id,
                    login=event.login.model_dump(mode="json"),
                    features=event.features.model_dump() if event.features else None,
                    occurred_at=event.occurred_at,
                )
            )
            session.add(ProcessedEvent(event_id=event.event_id))
            session.commit()
            logger.info(
                "profile updated user_id=%s event_id=%s login_count=%s",
                event.user_id,
                event.event_id,
                updated.login_count,
            )
            return True
