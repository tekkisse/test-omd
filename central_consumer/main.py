import logging

from .config import Settings
from .omd_client import OMDClient
from .sync_handler import SyncHandler
from .consumer import RabbitMQConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    settings = Settings()
    omd_client = OMDClient(settings.central_omd_url, settings.central_omd_token)
    handler = SyncHandler(omd_client, settings)
    consumer = RabbitMQConsumer(settings, handler)

    logger.info("Central OMD sync consumer starting")
    try:
        consumer.run()
    finally:
        omd_client.close()


if __name__ == "__main__":
    main()
