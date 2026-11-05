"""What the consumer did, for Prometheus: outcomes and how far behind it runs."""

from __future__ import annotations

from datetime import datetime, timezone

from prometheus_client import Counter, Histogram

CONSUMED = Counter(
    "rba_events_consumed_total",
    "Events taken off the queue, by outcome (applied, dead_lettered), and retries (retried).",
    ["consumer", "outcome"],
)
# From the decision to its effect on the profile: journal + relay + queue + handler.
LAG = Histogram(
    "rba_event_lag_seconds",
    "Seconds from the event's occurred_at to the consumer applying it.",
    ["consumer"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 300, 900),
)


def observe_lag(consumer: str, occurred_at: datetime) -> None:
    at = occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=timezone.utc)
    LAG.labels(consumer).observe(max(0.0, (datetime.now(timezone.utc) - at).total_seconds()))
