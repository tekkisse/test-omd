import logging
import threading

import pika
import pika.exceptions

from shared.events import SiteEvent
from .config import Settings

logger = logging.getLogger(__name__)

_DELIVERY_PERSISTENT = 2


class RabbitMQPublisher:
    """Thread-safe, auto-reconnecting RabbitMQ publisher."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
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
        logger.info("RabbitMQ publisher connected to %s", self._settings.rabbitmq_url)

    def close(self) -> None:
        try:
            if self._connection and not self._connection.is_closed:
                self._connection.close()
        except Exception:
            pass

    def _ensure_connected(self) -> None:
        if self._connection is None or self._connection.is_closed:
            self.connect()
        elif self._channel is None or self._channel.is_closed:
            self._channel = self._connection.channel()
            self._channel.exchange_declare(
                exchange=self._settings.rabbitmq_exchange,
                exchange_type="topic",
                durable=True,
            )

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(self, site_event: SiteEvent) -> None:
        routing_key = ".".join([
            site_event.site_code,
            site_event.event.entityType,
            site_event.event.eventType,
        ])
        body = site_event.model_dump_json().encode()

        with self._lock:
            try:
                self._ensure_connected()
                self._channel.basic_publish(  # type: ignore[union-attr]
                    exchange=self._settings.rabbitmq_exchange,
                    routing_key=routing_key,
                    body=body,
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=_DELIVERY_PERSISTENT,
                    ),
                )
                logger.info("Published [%s]", routing_key)
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as exc:
                logger.warning("RabbitMQ connection lost (%s), reconnecting…", exc)
                self._connection = None
                self._ensure_connected()
                self._channel.basic_publish(  # type: ignore[union-attr]
                    exchange=self._settings.rabbitmq_exchange,
                    routing_key=routing_key,
                    body=body,
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=_DELIVERY_PERSISTENT,
                    ),
                )
                logger.info("Published [%s] after reconnect", routing_key)
