#validation.py: verificação da estrutura e dos tipos dos dados.
RACE_TYPES = ["RAC", "SPR"]

def _find_orphans(db, child, local_field, parent) -> dict:
    total = db[child].count_documents({})
    orphans = list(db[child].aggregate([
        { "$lookup": { "from": parent, "localField": local_field, "foreignField": "_id", "as": "parent_docs" } },
        { "$match": { "parent_docs": { "$size": 0 } } },
        { "$project": { local_field: 1 } },
    ]))

    return {
        "total": total,
        "failures": len(orphans),
        "examples": orphans[:5],
    }


def _find_missing(db, field, session_filter=None) -> dict:
    base = [
        { "$lookup": { "from": "sessions", "localField": "session_id", "foreignField": "_id", "as": "s" } },
        { "$unwind": "$s" },
    ]
    if session_filter is not None:
        base.append({ "$match": { "s.type": session_filter } })

    total_list = list(db["classification"].aggregate(base + [
        { "$count": "n"}
    ]))

    total = total_list[0]["n"] if total_list else 0

    missing_list = list(db["classification"].aggregate(base + [
        { "$match": { field: {"$in": [None, ""]} } },
        { "$project": { field: 1, "status": 1, "rider.full_name": 1, "s.type": 1} },
    ]))

    missing_pct = round(len(missing_list) / total * 100, 2) if total else 0

    return {
        "total": total,
        "failures": len(missing_list),
        "missing_pct": missing_pct,
        "examples": missing_list[:5],
    }


def check_unique_session_rider(db) -> dict:
    group_stage = { "$group": {
        "_id": { "session_id": "$session_id", "rider_id": "$rider_id" },
        "count": { "$sum": 1 },
    }}

    duplicates = list(db["classification"].aggregate([
        group_stage,
        {"$match": {"count": {"$gt": 1}}}
    ]))

    total_result = list(db["classification"].aggregate([
        group_stage,
        { "$count": "count_groups" }
    ]))

    total = total_result[0]["count_groups"] if total_result else 0

    return {
        "rule": "classification_unique_session_rider",
        "dimension": "uniqueness",
        "total": total,
        "failures": len(duplicates),
        "examples": duplicates[:5],
    }


def check_classification_session_ref(db) -> dict:
    result = _find_orphans(db, "classification", "session_id", "sessions")
    return {
        "rule": "classification_session_ref",
        "dimension": "referential_integrity",
        **result,
    }


def check_session_event_ref(db) -> dict:
    result = _find_orphans(db, "sessions", "event.id", "events")
    return {
        "rule": "session_event_ref",
        "dimension": "referential_integrity",
        **result,
    }


def check_best_lap_completeness(db) -> dict:
    result = _find_missing(db, "best_lap.time", {"$nin": RACE_TYPES})
    return {
        "rule": "best_lap_completeness",
        "dimension": "completeness",
        **result,
    }


def check_position_completeness(db) -> dict:
    result = _find_missing(db, "position")
    return {
        "rule": "position_completeness",
        "dimension": "completeness",
        **result,
    }


def check_gap_completeness(db) -> dict:
    result = _find_missing(db, "gap.first")
    return {
        "rule": "gap_completeness",
        "dimension": "completeness",
        **result,
    }


def check_position_sequence(db) -> dict:
    base = [
        { "$match": { "position": { "$ne": None } } },
        { "$group": {
            "_id": "$session_id",
            "n": { "$sum": 1 },
            "min": { "$min": "$position" },
            "max": { "$max": "$position" },
            "distinct": { "$addToSet": "$position" }
            }
        },
    ]

    failure_filter = [
        {"$project": {"n": 1, "min": 1, "max": 1, "n_distinct": {"$size": "$distinct"} }},
        {"$match": {"$expr": {"$or": [
            { "$ne": ["$min", 1]},
            { "$ne": ["$max", "$n"]},
            { "$ne": ["$n_distinct", "$n"]},
        ]}}}
    ]

    failures = list(db["classification"].aggregate(base + failure_filter))

    total_result = list(db["classification"].aggregate(base + [
        {"$count": "count_groups"}
    ]))

    total = total_result[0]["count_groups"] if total_result else 0

    return {
        "rule": "position_sequence",
        "dimension": "validity",
        "total": total,
        "failures": len(failures),
        "examples": failures[:5],
    }