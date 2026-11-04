"""Consume DecisionMade / LoginConfirmed from RabbitMQ and update profiles."""

from __future__ import annotations

import json
import logging

import pika
from prometheus_client import start_http_server
from rba_contracts import DecisionMadeEvent, LoginConfirmedEvent
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rba_profile_service.config import Settings, get_settings
from rba_profile_service.handler import ProfileUpdater
from rba_profile_service.init import initialise
from rba_profile_service.metrics import CONSUMED, observe_lag

logger = logging.getLogger(__name__)
CONSUMER = "profile"


def declare(ch, settings: Settings) -> None:
    """The queue, bound to both channels, and its dead-letter queue.

    A queue's arguments are fixed when it is first declared: a queue left from
    before the dead-letter queue existed must be deleted once (empty) so it is
    declared again with them.
    """
    ch.exchange_declare(exchange=settings.exchange_name, exchange_type="topic", durable=True)
    ch.exchange_declare(exchange=settings.dead_letter_exchange, exchange_type="direct", durable=True)
    dlq = f"{settings.queue_name}.dlq"
    ch.queue_declare(queue=dlq, durable=True)
    ch.queue_bind(queue=dlq, exchange=settings.dead_letter_exchange, routing_key=settings.queue_name)
    ch.queue_declare(
        queue=settings.queue_name,
        durable=True,
        arguments={
            "x-dead-letter-exchange": settings.dead_letter_exchange,
            "x-dead-letter-routing-key": settings.queue_name,
        },
    )
    for routing_key in (settings.routing_key, settings.confirmed_routing_key):
        ch.queue_bind(
            queue=settings.queue_name,
            exchange=settings.exchange_name,
            routing_key=routing_key,
        )


def run(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    engine = create_engine(settings.database_url, future=True)
    if settings.init_on_startup:
        initialise(settings, engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    updater = ProfileUpdater(
        redis_url=settings.redis_url,
        key_prefix=settings.redis_key_prefix,
        session_factory=factory,
        population_key=settings.redis_population_key,
    )

    if settings.metrics_port:
        start_http_server(settings.metrics_port)
    params = pika.URLParameters(settings.rabbitmq_url)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    declare(ch, settings)
    ch.basic_qos(prefetch_count=1)

    def _on_message(channel, method, properties, body: bytes) -> None:
        try:
            # The publisher stamps the channel in `type`; a replayed message
            # (rba_event_publisher.dlq) arrives with the queue as routing key.
            kind = properties.type or method.routing_key
            if kind == settings.confirmed_routing_key:
                event = LoginConfirmedEvent.model_validate_json(body)
                updater.handle_confirmed(event)
            else:
                event = DecisionMadeEvent.model_validate_json(body)
                updater.handle(event)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            CONSUMED.labels(CONSUMER, "applied").inc()
            observe_lag(CONSUMER, event.occurred_at)
            if settings.once:
                channel.stop_consuming()
        except Exception:
            logger.exception("handler failed; dead-lettered to %s.dlq", settings.queue_name)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            CONSUMED.labels(CONSUMER, "dead_lettered").inc()

    ch.basic_consume(queue=settings.queue_name, on_message_callback=_on_message)
    logger.info("profile-service consuming queue=%s", settings.queue_name)
    try:
        ch.start_consuming()
    finally:
        conn.close()


def main() -> None:
    run()


if __name__ == "__main__":
    main()
