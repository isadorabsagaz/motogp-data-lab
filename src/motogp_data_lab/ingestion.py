#ingestion.py: coordenação da coleta e sequência das chamadas.
#EVENT -> SESSION -> CLASSIFICATION

import logging
from src.motogp_data_lab.api_client import get_events, get_sessions, get_classification
from src.motogp_data_lab.storage import MongoStorage

logger = logging.getLogger(__name__)

SEASON_ID = "ae6c6f0d-c652-44f8-94aa-420fc5b3dab4"
CATEGORY_ID = "e8c110ad-64aa-4e8e-8a86-f2f152f6a942"
SEASON_YEAR = 2025

def collect_season(storage: MongoStorage):
    #1. search for events of the season
    events = get_events(season_id=SEASON_ID)

    # FILTRO A SER REMOVIDO! APENAS THAILANDIA 2025
    events = [
        event
        for event in events
        if event.get("short_name") == "THA"
    ]

    if not events:
        logger.warning("No events in THA found")
        return

    logger.info("quant eventos: %s", len(events))

    storage.upsert_many("events", events, "results/events")

    #2. search for sessions in each event
    for event in events:
        event_id = event["id"]

        sessions = get_sessions(event_id=event_id, category_id=CATEGORY_ID)

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
                    "season_year": SEASON_YEAR,
                    "category_id": CATEGORY_ID,
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
