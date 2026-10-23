"""DecisionMadeEvent → Redis profile + history row (no Redis or Postgres needed)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4, uuid5

from rba_contracts import (
    Action,
    DecisionMadeEvent,
    EngineMode,
    LoginConfirmedEvent,
    LoginEventSnapshot,
    RiskLevel,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rba_profile_service.db import Base, ProfileHistoryRow
from rba_profile_service.handler import ProfileUpdater


class _DictRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.hashes: dict[str, dict[str, int]] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value

    def hincrby(self, key: str, field: str, amount: int) -> None:
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = bucket.get(field, 0) + amount


def _updater() -> tuple[ProfileUpdater, _DictRedis, sessionmaker]:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    updater = ProfileUpdater(redis_url="redis://unused", key_prefix="rba:profile:", session_factory=factory)
    fake = _DictRedis()
    updater._redis = fake
    return updater, fake, factory


def _event() -> DecisionMadeEvent:
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    return DecisionMadeEvent(
        event_id=uuid4(),
        occurred_at=now,
        tenant_id="kaze-labs",
        application_id="kaze-portal",
        user_id="usr_lucas",
        risk_score=0.1,
        risk_level=RiskLevel.LOW,
        action=Action.ALLOW,
        enforced_action=Action.ALLOW,
        engine_mode=EngineMode.ACTIVE,
        model_version="freeman-0.2.0",
        policy_version="2.0.0",
        feature_schema_version="1.0.0",
        login=LoginEventSnapshot(login_timestamp=now, ip_address="203.0.113.10", country="AR", asn="7303"),
    )


def test_applies_once_and_records_the_tenant() -> None:
    updater, fake, factory = _updater()
    event = _event()
    assert updater.handle(event) is True
    assert updater.handle(event) is False  # idempotent on event_id

    profile = json.loads(fake.data["rba:profile:usr_lucas"])
    assert profile["login_count"] == 1
    with factory() as session:
        rows = list(session.scalars(select(ProfileHistoryRow)))
    assert [(r.tenant_id, r.user_id) for r in rows] == [("kaze-labs", "usr_lucas")]


def _confirmation(decision: DecisionMadeEvent) -> LoginConfirmedEvent:
    return LoginConfirmedEvent(
        event_id=uuid5(decision.event_id, "login-confirmed"),
        decision_event_id=decision.event_id,
        occurred_at=decision.occurred_at,
        tenant_id=decision.tenant_id,
        application_id=decision.application_id,
        user_id=decision.user_id,
        login=decision.login,
    )


def test_a_step_up_is_learned_only_when_passed() -> None:
    """ADR-0042: an attacker with the password but not the passkey teaches nothing."""
    updater, fake, _ = _updater()
    decision = _event().model_copy(update={"enforced_action": Action.REQUIRE_MFA})

    assert updater.handle(decision) is False
    assert "rba:profile:usr_lucas" not in fake.data

    assert updater.handle_confirmed(_confirmation(decision)) is True
    assert updater.handle_confirmed(_confirmation(decision)) is False
    assert json.loads(fake.data["rba:profile:usr_lucas"])["login_count"] == 1


def test_a_blocked_login_is_never_learned_and_a_failure_only_counts() -> None:
    updater, fake, _ = _updater()
    assert updater.handle(_event().model_copy(update={"enforced_action": Action.BLOCK})) is False
    assert "rba:profile:usr_lucas" not in fake.data

    failed = _event()
    failed = failed.model_copy(
        update={
            "enforced_action": Action.BLOCK,
            "login": failed.login.model_copy(update={"login_successful": False}),
        }
    )
    assert updater.handle(failed) is True
    profile = json.loads(fake.data["rba:profile:usr_lucas"])
    assert (profile["login_count"], len(profile["failed_login_ts"])) == (0, 1)


def test_only_learned_logins_join_the_population() -> None:
    """ADR-0042: the PDP's population prior counts learned logins, nothing else."""
    updater, fake, _ = _updater()
    updater.handle(_event().model_copy(update={"enforced_action": Action.REQUIRE_MFA}))
    failed = _event()
    updater.handle(failed.model_copy(update={"login": failed.login.model_copy(update={"login_successful": False})}))
    assert fake.hashes == {}

    updater.handle(_event())
    population = fake.hashes["rba:population"]
    assert population["_total"] == 1 and population["country=AR"] == 1
