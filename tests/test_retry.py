"""Transient failures are retried with the configured waits; bad messages are not."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from rba_profile_service.retry import apply_with_retries


class _Flaky:
    def __init__(self, failures: int, exc: Exception) -> None:
        self.failures = failures
        self.exc = exc
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return "applied"


def test_a_blip_is_retried_until_it_clears() -> None:
    waits: list[float] = []
    retried: list[int] = []
    flaky = _Flaky(2, ConnectionError("db down"))
    result = apply_with_retries(
        flaky, delays=(0.5, 2, 8), sleep=waits.append, on_retry=lambda n, _: retried.append(n)
    )
    assert result == "applied"
    assert flaky.calls == 3
    assert waits == [0.5, 2]
    assert retried == [1, 2]


def test_an_outage_longer_than_the_waits_is_raised() -> None:
    waits: list[float] = []
    flaky = _Flaky(10, ConnectionError("db down"))
    with pytest.raises(ConnectionError):
        apply_with_retries(flaky, delays=(0.5, 2, 8), sleep=waits.append)
    assert flaky.calls == 4
    assert waits == [0.5, 2, 8]


def test_a_malformed_message_is_not_retried() -> None:
    class Event(BaseModel):
        n: int

    waits: list[float] = []

    def parse() -> Event:
        return Event.model_validate_json(b'{"n": "x"}')

    with pytest.raises(ValidationError):
        apply_with_retries(parse, delays=(0.5, 2, 8), sleep=waits.append)
    assert waits == []
