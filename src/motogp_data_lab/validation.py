#validation.py: verificação da estrutura e dos tipos dos dados.

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