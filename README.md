# rba-profile-service

Consumes `rba.decision.made.v1`, updates Redis `ProfileState` via
`rba-features.update_profile`, and appends history in `rba_profile`.
Idempotent on `event_id`.

## Setup

```bash
cd ../rba-infra && docker compose up -d && cd -
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../rba-features -e ../rba-contracts -e ".[dev]"
rba-profile-service
```

When this service owns Redis writes, run decision-service with
`PROFILE_WRITE_MODE=none`.
