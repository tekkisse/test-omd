from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # RabbitMQ
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "omd.sync"
    rabbitmq_queue: str = "omd.central.sync"
    # "#" receives everything; use "SITE_A.#" to limit to one site
    rabbitmq_routing_key: str = "#"
    rabbitmq_prefetch: int = 10

    # Central OpenMetadata instance
    central_omd_url: str = "http://localhost:8585"
    central_omd_token: str  # JWT or API key from OMD

    # How to handle deletions from sites (log | soft_delete | hard_delete)
    deletion_strategy: str = "soft_delete"
