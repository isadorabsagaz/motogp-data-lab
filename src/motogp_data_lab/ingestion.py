#ingestion.py: coordenação da coleta e sequência das chamadas.
#EVENT -> SESSION -> CLASSIFICATION

import logging
from src.motogp_data_lab.api_client import get_events, get_sessions, get_classification, get_seasons, get_categories
from src.motogp_data_lab.storage import MongoStorage

logger = logging.getLogger(__name__)

def resolve_season_id(year: int) -> str:
    seasons = get_seasons()
    for season in seasons:
        if season["year"] == year:
            return season["id"]

    raise ValueError(f"Season {year} not found / does not exist")

def resolve_category_id(season_id: str, name: str) -> str:
    categories = get_categories(season_id)
    name = name.replace("™", "").lower()

    for category in categories:
        category_name = category["name"].replace("™", "").lower()
        if category_name == name:
            return category["id"]

    raise ValueError(f"Category {name} not found / does not exist")

def collect_season(storage: MongoStorage, season_year: int, category_name: str, event_short: str | None = None):
    #1. search for events of the season
    season_id = resolve_season_id(season_year)
    category_id = resolve_category_id(season_id, category_name)
    events = get_events(season_id)

    # FILTER FOR SHORT_NAME AND IGNORE TESTS
    events = [
        event
        for event in events
            if not event.get("test")
        ]

    if event_short is not None:
        events = [
            event
            for event in events
                if event.get("short_name") == event_short
        ]

    if not events:
        logger.warning("No events found (season=%s, event=%s)", season_year, event_short)
        return

    logger.info("quant eventos: %s", len(events))

    storage.upsert_many("events", events, "results/events")

    #2. search for sessions in each event
    for event in events:
        event_id = event["id"]

        sessions = get_sessions(event_id=event_id, category_id=category_id)

        logger.info("%s: %s sessions", event.get("short_name", event_id), len(sessions))

        storage.upsert_many("sessions", sessions, "results/sessions")

        for session in sessions:
            session_id = session["id"]

            #3. search for classification in each session
            result = get_classification(session_id=session_id)

            classification = result.get("classification", [])

            #4. storage the results
            classification_list = []
            for item in classification:
                rider = item.get("rider", {})

                document = {
                    **item,
                    "session_id": session_id,
                    "event_id": event_id,
                    "season_year": season_year,
                    "category_id": category_id,
                    "rider_id": rider.get("id"),
                }

                classification_list.append(document)

            write_result = storage.upsert_many(
                "classification", classification_list, "results/session/{session_id}/classification"
            )

            if write_result is not None:
                logger.info(
                    "Session %s: %s results (upserted=%s, matched=%s, modified=%s)",
                    session.get("type"), len(classification),
                    write_result.upserted_count, write_result.matched_count, write_result.modified_count,
                )
            else:
                logger.warning("Session %s (%s) without classification", session.get("type"), session_id)
