"""Retry a handler on transient errors before the message is dead-lettered.

A database or Valkey blip clears in seconds; without this, every event that
arrived during it would wait in the dead-letter queue for a manual replay.
The retries happen in place, holding the message (prefetch = 1), so a
decision and its confirmation are still applied in the order published.

A message that cannot be parsed is not retried: a ValueError (pydantic's
ValidationError and JSON errors are ones) will fail the same way every time.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def apply_with_retries(
    apply: Callable[[], T],
    *,
    delays: Sequence[float],
    sleep: Callable[[float], None],
    on_retry: Callable[[int, Exception], None] = lambda attempt, exc: None,
) -> T:
    """Run `apply`; after a transient failure wait delays[i] and try again.

    One attempt plus one per delay. The last failure, or the first permanent
    one, is raised for the caller to dead-letter.
    """
    for attempt, delay in enumerate((*delays, None), start=1):
        try:
            return apply()
        except ValueError:
            raise
        except Exception as exc:
            if delay is None:
                raise
            on_retry(attempt, exc)
            sleep(delay)
    raise AssertionError("unreachable")
