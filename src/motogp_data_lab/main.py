import logging
import argparse
from src.motogp_data_lab import config
from src.motogp_data_lab.ingestion import collect_season
from src.motogp_data_lab.storage import MongoStorage

logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser(description="Collect season data")
    parser.add_argument("--season", type=int, default=2025, help="Season year")
    parser.add_argument("--category", type=str, default="MotoGP", help="category's name without the ™")
    parser.add_argument("--event", type=str, default=None, help="event's short_name - ex. THA")
    parser.add_argument("--force", action="store_true", help="Force overwrite of existing data")
    return parser.parse_args()

def main():
    args = parse_args()

    logging.basicConfig(
        level=config.LOG_LEVEL.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logger.info("[ARGS] Collecting season=%s category=%s event=%s force=%s", args.season, args.category, args.event, args.force)

    storage = MongoStorage(config.MONGO_URI, config.MONGO_DB)

    try:
        storage.ping()
        logger.info("MongoDB connected")

        storage.ensure_indexes()
        logger.info("MongoDB indexes created")

        collect_season(storage=storage, season_year=args.season, category_name=args.category, event_short=args.event, force=args.force)
        logger.info("Season Collection completed")

    except Exception:
        logger.exception("Pipeline failed")
        raise

    finally:
        storage.close()

if __name__ == "__main__":
    main()