import logging
from src.motogp_data_lab import config
from src.motogp_data_lab.ingestion import collect_season
from src.motogp_data_lab.storage import MongoStorage

logger = logging.getLogger(__name__)

def main():
    logging.basicConfig(
        level=config.LOG_LEVEL.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    storage = MongoStorage(config.MONGO_URI, config.MONGO_DB)

    try:
        storage.ping()
        logger.info("MongoDB connected")

        collect_season(storage)
        logger.info("Season Collection completed")

    except Exception:
        logger.exception("Pipeline failed")
        raise

    finally:
        storage.close()

if __name__ == "__main__":
    main()