from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Identity of this site — set per deployment
    site_code: str  # e.g. SITE_A  (alphanumeric + underscore, no dots)

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "omd.sync"

    # Optional HMAC secret configured in the OMD Event Subscription
    webhook_secret: Optional[str] = None

    # Port this service listens on
    port: int = 8080
