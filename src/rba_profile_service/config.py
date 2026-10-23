from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from rba_contracts.events import DECISION_MADE_CHANNEL, LOGIN_CONFIRMED_CHANNEL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://rba:rba@localhost:5432/rba_profile"
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "rba:profile:"
    # ADR-0042: learned-login counts, the PDP's population prior.
    redis_population_key: str = "rba:population"
    rabbitmq_url: str = "amqp://rba:rba@localhost:5672/"
    exchange_name: str = "rba.events"
    queue_name: str = "rba.profile.decision-made.v1"
    routing_key: str = DECISION_MADE_CHANNEL
    # ADR-0042: step-ups are learned when passed. Same queue, so a decision and
    # its confirmation are applied in the order they were published.
    confirmed_routing_key: str = LOGIN_CONFIRMED_CHANNEL
    once: bool = False  # process one message then exit (tests)
    # C-4: create tables and seed home profiles at startup (compose, k3d).
    # Off where `python -m rba_profile_service.init` runs as a Job first.
    init_on_startup: bool = True
    # Users given a usual home history (the TEST-NET home, ADR-0022) so the
    # local walkthrough's first login can ALLOW. The two Martíns (ADR-0035).
    seed_profile_user_ids: str = "usr_rb_martin,usr_kz_martin"

    def profile_user_ids(self) -> list[str]:
        return [part.strip() for part in self.seed_profile_user_ids.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
