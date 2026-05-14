"""
RabbitMQ consumer for the central sync service.

Uses a single durable queue bound to the topic exchange with routing key "#"
so every site's events are consumed.  Messages are acked only after a
successful sync; on failure they are nacked with requeue=True so RabbitMQ
will redeliver them (add a dead-letter exchange in production).
"""
from __future__ import annotations

import json
import logging
import time

import pika
import pika.exceptions

from shared.events import SiteEvent
from .config import Settings
from .sync_handler import SyncHandler

logger = logging.getLogger(__name__)

_RETRY_DELAY_S = 5


class RabbitMQConsumer:
    def __init__(self, settings: Settings, handler: SyncHandler) -> None:
        self._settings = settings
        self._handler = handler
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        params = pika.URLParameters(self._settings.rabbitmq_url)
        params.heartbeat = 60
        params.blocked_connection_timeout = 10
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()
        self._channel.exchange_declare(
            exchange=self._settings.rabbitmq_exchange,
            exchange_type="topic",
            durable=True,
        )
        self._channel.queue_declare(queue=self._settings.rabbitmq_queue, durable=True)
        self._channel.queue_bind(
            queue=self._settings.rabbitmq_queue,
            exchange=self._settings.rabbitmq_exchange,
            routing_key=self._settings.rabbitmq_routing_key,
        )
        self._channel.basic_qos(prefetch_count=self._settings.rabbitmq_prefetch)
        self._channel.basic_consume(
            queue=self._settings.rabbitmq_queue,
            on_message_callback=self._on_message,
        )
        logger.info(
            "Consumer ready — exchange=%s queue=%s routing=%s",
            self._settings.rabbitmq_exchange,
            self._settings.rabbitmq_queue,
            self._settings.rabbitmq_routing_key,
        )

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def _on_message(
        self,
        channel: pika.adapters.blocking_connection.BlockingChannel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ) -> None:
        routing_key = method.routing_key
        try:
            raw = json.loads(body)
            site_event = SiteEvent(**raw)
            self._handler.handle(site_event)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as exc:
            logger.error("Failed to process message [%s]: %s", routing_key, exc, exc_info=True)
            # Requeue once; a dead-letter queue should handle persistent failures
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=not method.redelivered)

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        while True:
            try:
                self._connect()
                assert self._channel is not None
                self._channel.start_consuming()
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError) as exc:
                logger.warning("RabbitMQ connection lost (%s), retrying in %ds…", exc, _RETRY_DELAY_S)
                time.sleep(_RETRY_DELAY_S)
            except KeyboardInterrupt:
                logger.info("Shutting down consumer")
                if self._channel and self._channel.is_open:
                    self._channel.stop_consuming()
                break
            finally:
                if self._connection and not self._connection.is_closed:
                    try:
                        self._connection.close()
                    except Exception:
                        pass
