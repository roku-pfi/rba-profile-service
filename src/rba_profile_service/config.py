from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from rba_contracts.events import DECISION_MADE_CHANNEL, LOGIN_CONFIRMED_CHANNEL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://rba:rba@localhost:5432/rba_profile"
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "rba:profile:"
    # ADR-0042: learned-login counts, the PDP's population prior. One hash per
    # tenant under this base, "<base>:<tenant_id>" (ADR-0046).
    redis_population_key: str = "rba:population"
    rabbitmq_url: str = "amqp://rba:rba@localhost:5672/"
    exchange_name: str = "rba.events"
    queue_name: str = "rba.profile.decision-made.v1"
    # A message the handler cannot apply goes to "<queue_name>.dlq" through
    # this exchange, not away; `python -m rba_event_publisher.dlq` replays it.
    dead_letter_exchange: str = "rba.events.dlx"
    metrics_port: int = 9102  # Prometheus; 0 turns it off
    routing_key: str = DECISION_MADE_CHANNEL
    # ADR-0042: step-ups are learned when passed. Same queue, so a decision and
    # its confirmation are applied in the order they were published.
    confirmed_routing_key: str = LOGIN_CONFIRMED_CHANNEL
    once: bool = False  # process one message then exit (tests)
    # C-4: create tables and seed home profiles at startup (compose, k3d).
    # Off where `python -m rba_profile_service.init` runs as a Job first.
    init_on_startup: bool = True
    # Users given a usual home history (the TEST-NET home, ADR-0022) so the
    # local walkthrough's first login can ALLOW. The two Martíns (ADR-0035),
    # each as "<tenant_id>:<user_id>" so the history joins its tenant's
    # population (ADR-0046).
    seed_profile_user_ids: str = "roku-bank:usr_rb_martin,kaze-labs:usr_kz_martin"

    def profile_seeds(self) -> list[tuple[str, str]]:
        """(tenant_id, user_id) of every user given a home history."""
        seeds = []
        for part in self.seed_profile_user_ids.split(","):
            tenant_id, sep, user_id = part.strip().partition(":")
            if not sep or not tenant_id or not user_id:
                if part.strip():
                    raise ValueError(f"SEED_PROFILE_USER_IDS entry {part.strip()!r} is not <tenant_id>:<user_id>")
                continue
            seeds.append((tenant_id, user_id))
        return seeds


@lru_cache
def get_settings() -> Settings:
    return Settings()
