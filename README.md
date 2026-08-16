# rba-profile-service

Async consumer of `rba.decision.made.v1`. Updates Redis `ProfileState` via
`rba-features.update_profile` and appends a history row in Postgres
`rba_profile`. **Idempotent on `event_id`.**

This is the Phase 4 owner of Redis **writes**. When it is running, start
decision-service with `PROFILE_WRITE_MODE=none` so the PDP only **reads**
profiles (train/serve still uses the same `update_profile`).

Package version: **0.1.0**. CLI: `rba-profile-service`.

> Status: [`../docs/plans/status.md`](../docs/plans/status.md).
> ADR-0011. AI: [`AGENTS.md`](AGENTS.md).

## What it does

```
RabbitMQ  rba.events / rba.decision.made.v1
    queue rba.profile.decision-made.v1
        → skip if event_id already in processed_events
        → if login snapshot missing: mark processed, do not update Redis
        → GET Redis rba:profile:{user_id}
        → update_profile(profile, login.to_feature_event())
        → SET Redis
        → INSERT profile_history + processed_events
        → ACK
```

Handler failures **nack without requeue** (no DLQ yet). Prefetch = 1.

`tests/` exists but has no cases yet (thin slice).

## Layout

```
src/rba_profile_service/
├── main.py      # pika consumer loop
├── config.py
├── handler.py   # ProfileUpdater (Redis + Postgres)
└── db.py        # processed_events, profile_history
```

### Postgres tables (DB `rba_profile`)

Created on startup:

- `processed_events` — PK `event_id` (idempotency ledger)
- `profile_history` — unique `event_id`; login snapshot + optional features

Redis key: `{REDIS_KEY_PREFIX}{user_id}` (default `rba:profile:`), JSON from
`profile_to_dict`.

## Setup

```bash
cd ../rba-infra && docker compose up -d && cd -

python3 -m venv .venv && source .venv/bin/activate
pip install -e ../rba-features -e ../rba-contracts -e ".[dev]"
rba-profile-service
```

Requires the publisher (and a PDP that writes outbox rows with `login` set).

`ONCE=true` processes one message then exits (tests / smoke).

Image (from polyrepo root): `docker build -f rba-profile-service/Dockerfile -t rba-profile-service:dev .`
Cluster: `../rba-infra/scripts/k3d-up.sh`.

## Env

| Variable | Default |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://rba:rba@localhost:5432/rba_profile` |
| `REDIS_URL` | `redis://localhost:6379/0` |
| `REDIS_KEY_PREFIX` | `rba:profile:` |
| `RABBITMQ_URL` | `amqp://rba:rba@localhost:5672/` |
| `EXCHANGE_NAME` | `rba.events` |
| `QUEUE_NAME` | `rba.profile.decision-made.v1` |
| `ROUTING_KEY` | `rba.decision.made.v1` |
| `ONCE` | `false` |

## Guardrails

- Profile updates use `rba-features.update_profile` only — no re-implemented
  feature logic.
- Owns `rba_profile` + Redis profile keys; does not own the decision DB.
- Missing values still follow the feature-library contract (not added to
  seen-sets).

## Status

Phase 4 thin slice. k8s Deployment via `../rba-infra` Helm (K8s-1). Remaining:
DLQ. Roadmap: `../docs/plans/status.md`.
