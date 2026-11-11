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