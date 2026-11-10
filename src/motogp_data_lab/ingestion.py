#ingestion.py: coordenação da coleta e sequência das chamadas.
#EVENT -> SESSION -> CLASSIFICATION -> GRID -> STANDINGS -> TEAMS -> RIDERS

import logging

from src.motogp_data_lab.api_client import get_events, get_sessions, get_classification, get_seasons, get_categories, get_grid, get_standings, get_broadcast_categories, get_teams, get_rider
from src.motogp_data_lab.storage import MongoStorage

logger = logging.getLogger(__name__)

def normalize_name(name: str) -> str:
    return name.lower().replace("™", "")

def resolve_season_id(year: int) -> str:
    seasons = get_seasons()
    for season in seasons:
        if season["year"] == year:
            return season["id"]

    raise ValueError(f"Season {year} not found / does not exist")

def resolve_category_id(season_id: str, name: str) -> str:
    categories = get_categories(season_id)
    name = normalize_name(name)

    for category in categories:
        category_name = normalize_name(category["name"])
        if category_name == name:
            return category["id"]

    raise ValueError(f"Category {name} not found / does not exist")

def resolve_broadcast_category(season_year: int, name: str) -> str:
    categories = get_broadcast_categories(season_year)
    name = normalize_name(name)

    for category in categories:
        category_name = normalize_name(category["name"])
        if category_name == name:
            return category["id"]

    raise ValueError(f"Broadcast Category {name} not found / does not exist")

COLLECTIONS = ("events", "sessions", "classification", "grid", "standings", "teams", "riders")

def _empty_stats() -> dict:
    # Todas as coleções aparecem sempre, mesmo com zero: o formato do documento em ingestion_runs não muda.
    stats = {
        collection: {"received": 0, "upserted": 0, "matched": 0, "modified": 0}
        for collection in COLLECTIONS
    }
    stats["sessions_skipped"] = 0
    return stats

def _add_counts(stats: dict, collection: str, label: str, received: int, write_result) -> None:
    # Soma (+=) em vez de atribuir: sessions, classification e grid passam aqui várias vezes por execução.
    counts = stats[collection]
    counts["received"] += received

    if write_result is None:
        logger.warning("%s %s: no results", collection, label)
        return

    counts["upserted"] += write_result.upserted_count
    counts["matched"] += write_result.matched_count
    counts["modified"] += write_result.modified_count

    logger.info(
        "%s %s: %s received (upserted=%s, matched=%s, modified=%s)",
        collection, label, received,
        write_result.upserted_count, write_result.matched_count, write_result.modified_count,
    )

def collect_season(
        storage: MongoStorage,
        season_year: int,
        category_name: str,
        event_short: str | None = None,
        force: bool = False
    ) -> dict:

    stats = _empty_stats()

    #1. search for events of the season
    season_id = resolve_season_id(season_year)
    category_id = resolve_category_id(season_id, category_name)
    broadcast_category_id = resolve_broadcast_category(season_year, category_name)

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
        return stats

    logger.info("quant eventos: %s", len(events))

    write_result = storage.upsert_many("events", events, "results/events")
    _add_counts(stats, "events", str(season_year), len(events), write_result)

    #2. search for sessions in each event
    for event in events:
        event_id = event["id"]

        event_label = event.get("short_name", event_id)

        sessions = get_sessions(event_id=event_id, category_id=category_id)

        write_result = storage.upsert_many("sessions", sessions, "results/sessions")
        _add_counts(stats, "sessions", event_label, len(sessions), write_result)

        for session in sessions:
            session_id = session["id"]

            #3. search for classification in each session
            session_with_classification = storage.has_classification(session_id)
            if session_with_classification and not force:
                logger.info("Session %s already have classification", session.get("id"))
                stats["sessions_skipped"] += 1
                continue

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

            _add_counts(
                stats, "classification", f"{event_label} {session.get('type')} ({session_id})",
                len(classification_list), write_result,
            )

        #5. collect grid results per event
        grid = get_grid(event_id=event_id, category_id=category_id)

        grid_list = []
        for item in grid:
            rider = item.get("rider", {})
            rider_id = rider.get("id")

            document = {
                **item,
                "event_id": event_id,
                "season_year": season_year,
                "category_id": category_id,
                "rider_id": rider_id,
                "id": f"{event_id}:{category_id}:{rider_id}"
            }

            grid_list.append(document)

        write_result = storage.upsert_many(
            "grid", grid_list, "results/event/{event_id}/category/{category_id}/grid"
        )

        _add_counts(stats, "grid", event_label, len(grid_list), write_result)

    #6. standings results
    result = get_standings(season_id=season_id, category_id=category_id)
    standings = result.get("classification", [])

    standing_list = []
    for item in standings:
        rider = item.get("rider", {})

        document = {
            **item,
            "season_year": season_year,
            "category_id": category_id,
            "rider_id": rider.get("id"),
        }
        standing_list.append(document)

    write_result = storage.upsert_many(
        "standings", standing_list, "results/standings"
    )

    _add_counts(stats, "standings", str(season_year), len(standing_list), write_result)

    #7. Teams
    teams = get_teams(category_id=broadcast_category_id, season_year=season_year)

    team_list = []
    for team in teams:
        team_id = team.get("id")
        document = {
            **team,
            "season_year": season_year,
            "category_id": category_id,
            "id": f"{season_year}:{category_id}:{team_id}",
            "team_id": team_id,
        }
        team_list.append(document)

    write_result = storage.upsert_many(
        "teams", team_list, "teams"
    )

    _add_counts(stats, "teams", str(season_year), len(team_list), write_result)

    # 8. Riders
    riders_id_list = storage.distinct_rider_uuids(season_year=season_year, category_id=category_id)
    riders_list = []
    for item in riders_id_list:
        rider = get_rider(rider_id=item)
        riders_list.append(rider)

    write_result = storage.upsert_many(
        "riders", riders_list, "riders/{rider_id}"
    )

    _add_counts(stats, "riders", str(season_year), len(riders_list), write_result)

    logger.info("Skipped %s sessions (already collected)", stats["sessions_skipped"])

    return stats
