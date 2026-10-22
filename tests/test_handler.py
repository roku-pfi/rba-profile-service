"""DecisionMadeEvent → Redis profile + history row (no Redis or Postgres needed)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from rba_contracts import Action, DecisionMadeEvent, EngineMode, LoginEventSnapshot, RiskLevel
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rba_profile_service.db import Base, ProfileHistoryRow
from rba_profile_service.handler import ProfileUpdater


class _DictRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value


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
