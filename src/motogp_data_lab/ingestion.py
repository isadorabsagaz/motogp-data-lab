#ingestion.py: coordenação da recolha e sequência das chamadas.

#EVENT -> SESSION -> CLASSIFICATION

import time

from src.motogp_data_lab.api_client import get_json
from src.motogp_data_lab.storage import MongoStorage

SEASON_ID = "ae6c6f0d-c652-44f8-94aa-420fc5b3dab4"
CATEGORY_ID = "e8c110ad-64aa-4e8e-8a86-f2f152f6a942"
SEASON_YEAR = 2025

def collect_season(storage: MongoStorage):
    #1. search for events of the season
    events = get_json(
        "results/events",
        {"seasonUuid": SEASON_ID},
    )

    # FILTRO A SER REMOVIDO! APENAS THAILANDIA 2025
    events = [
        event
        for event in events
        if event.get("short_name") == "THA"
    ]

    if not events:
        print("No events in THA found")
        return

    print("quant eventos: ", len(events))

    for event in events:
        storage.upsert("events", event)

    #2. search for sessions in each event
    for event in events:
        event_id = event["id"]

        sessions = get_json(
            "results/sessions",
            {
                "eventUuid": event_id,
                "categoryUuid": CATEGORY_ID,
            },
        )

        print(
            f'{event.get("short_name", event_id)}: '
            f"{len(sessions)} sessions "
        )

        for session in sessions:
            session_id = session["id"]
            storage.upsert("sessions", session)

            #3. search for classification in each session
            result = get_json(
                f"results/session/{session_id}/classification",
                {
                    "seasonYear": SEASON_YEAR,
                    "test": "false",
                },
            )

            classification = result.get("classification", [])

            #4. storage the results
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

                storage.upsert("classification", document)

            print(
                f' Session {session.get("type")}: '
                f"{len(classification)} results"
            )

            #avoid to send to many requests to fast
            time.sleep(0.2)

        time.sleep(0.2)