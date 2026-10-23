"""Apply DecisionMadeEvent / LoginConfirmedEvent to Redis ProfileState (idempotent)."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime
from uuid import UUID

import redis
from rba_contracts import DecisionMadeEvent, LoginConfirmedEvent, LoginEventSnapshot
from rba_features.features import learn_at_decision, update_profile
from rba_features.population import learn_population
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
        population_key: str = "rba:population",
    ) -> None:
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix
        self._population_key = population_key
        self._sessions = session_factory

    def _key(self, user_id: str) -> str:
        return f"{self._prefix}{user_id}"

    def handle(self, event: DecisionMadeEvent) -> bool:
        """Return True if the profile changed, False if duplicate / skipped.

        A decision that asked for a step-up is not learned here: it waits for
        LoginConfirmedEvent, so an abandoned step-up teaches nothing (ADR-0042).
        A simulated login (presenter override, ADR-0032) teaches nothing either.
        """
        if event.simulated:
            logger.info("event_id=%s simulated: not learned", event.event_id)
            return self._apply(event.event_id, learn=None)
        if event.login is None:
            logger.warning(
                "event_id=%s missing login snapshot — cannot update profile",
                event.event_id,
            )
            # Still mark processed so we do not retry forever without a login payload.
            return self._apply(event.event_id, learn=None)
        if not learn_at_decision(event.login.login_successful, event.enforced_action.value):
            logger.info(
                "event_id=%s enforced %s: learned only if the step-up is passed",
                event.event_id,
                event.enforced_action.value,
            )
            return self._apply(event.event_id, learn=None)
        return self._apply(
            event.event_id,
            learn=(event.user_id, event.tenant_id, event.application_id, event.login),
            features=event.features.model_dump() if event.features else None,
            occurred_at=event.occurred_at,
        )

    def handle_confirmed(self, event: LoginConfirmedEvent) -> bool:
        """The user passed the step-up: learn the decision's login now."""
        return self._apply(
            event.event_id,
            learn=(event.user_id, event.tenant_id, event.application_id, event.login),
            features=None,
            occurred_at=event.occurred_at,
        )

    def _apply(
        self,
        event_id: UUID,
        *,
        learn: tuple[str, str, str, LoginEventSnapshot] | None,
        features: dict | None = None,
        occurred_at: datetime | None = None,
    ) -> bool:
        with self._sessions() as session:
            if already_processed(session, event_id):
                logger.info("skip duplicate event_id=%s", event_id)
                return False
            if learn is None:
                session.add(ProcessedEvent(event_id=event_id))
                session.commit()
                return False

            user_id, tenant_id, application_id, login = learn
            raw = self._redis.get(self._key(user_id))
            profile = profile_from_dict(json.loads(raw) if raw else None)
            event = login.to_feature_event()
            updated = update_profile(deepcopy(profile), event)
            self._redis.set(self._key(user_id), json.dumps(profile_to_dict(updated)))
            if login.login_successful:
                # A learned login is part of the deployment's population.
                learn_population(
                    event, lambda field, n: self._redis.hincrby(self._population_key, field, n)
                )

            session.add(
                ProfileHistoryRow(
                    event_id=event_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    application_id=application_id,
                    login=login.model_dump(mode="json"),
                    features=features,
                    occurred_at=occurred_at,
                )
            )
            session.add(ProcessedEvent(event_id=event_id))
            session.commit()
            logger.info(
                "profile updated user_id=%s event_id=%s login_count=%s",
                user_id,
                event_id,
                updated.login_count,
            )
            return True
