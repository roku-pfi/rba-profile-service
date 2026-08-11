from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from rba_contracts.events import DECISION_MADE_CHANNEL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://rba:rba@localhost:5432/rba_profile"
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "rba:profile:"
    rabbitmq_url: str = "amqp://rba:rba@localhost:5672/"
    exchange_name: str = "rba.events"
    queue_name: str = "rba.profile.decision-made.v1"
    routing_key: str = DECISION_MADE_CHANNEL
    once: bool = False  # process one message then exit (tests)


@lru_cache
def get_settings() -> Settings:
    return Settings()
