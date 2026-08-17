# AGENTS.md — rba-profile-service

Async profile materialiser. Status: `../docs/plans/status.md`.

## Guardrails

- Profile updates use `rba-features.update_profile` only — no re-implemented logic.
- Idempotent on `event_id` (`processed_events`).
- Owns `rba_profile` DB + Redis profile keys; does not own decision DB.
- Demo-2 home-profile seed is `SET NX` on `usr_demo` — do not overwrite a live history.
