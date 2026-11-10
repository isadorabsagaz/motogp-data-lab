from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId

from src.motogp_data_lab.storage import MongoStorage

STORAGE = "src.motogp_data_lab.storage"


@pytest.fixture
def storage():
    # MongoClient trocado por mock: os testes não precisam de MongoDB rodando.
    with patch(f"{STORAGE}.MongoClient"):
        s = MongoStorage("mongodb://fake:27017", "test_db")
    s.db = MagicMock()
    return s


def runs_collection(storage):
    # db["qualquer"] devolve sempre o mesmo mock; por isso conferimos o nome usado.
    storage.db.__getitem__.assert_called_with("ingestion_runs")
    return storage.db.__getitem__.return_value


# ---------- start_run ----------

def test_start_run_inserts_running_document(storage):
    args = {"season": 2025, "category": "MotoGP", "event": None, "force": False}

    storage.start_run(args)

    collection = runs_collection(storage)
    collection.insert_one.assert_called_once()
    document = collection.insert_one.call_args.args[0]
    assert document["status"] == "running"
    assert document["args"] == args
    assert isinstance(document["started_at"], datetime)
    assert document["started_at"].tzinfo == timezone.utc


def test_start_run_returns_inserted_id_and_started_at(storage):
    fake_id = ObjectId()
    storage.db.__getitem__.return_value.insert_one.return_value.inserted_id = fake_id

    run_id, started_at = storage.start_run({"season": 2025})

    assert run_id == fake_id
    # O started_at devolvido é o mesmo que foi gravado no banco.
    document = runs_collection(storage).insert_one.call_args.args[0]
    assert started_at == document["started_at"]


# ---------- finish_run ----------

def test_finish_run_updates_by_run_id(storage):
    run_id = ObjectId()
    started_at = datetime.now(timezone.utc)

    storage.finish_run(run_id, "success", started_at, {"requests": 10})

    collection = runs_collection(storage)
    collection.update_one.assert_called_once()
    filter_, update = collection.update_one.call_args.args
    assert filter_ == {"_id": run_id}
    fields = update["$set"]
    assert fields["status"] == "success"
    assert fields["stats"] == {"requests": 10}
    assert fields["error"] is None
    assert fields["finished_at"] >= started_at


def test_finish_run_does_not_upsert(storage):
    # O documento já existe desde o start_run; se não existir, é bug e não deve ser criado em silêncio.
    storage.finish_run(ObjectId(), "success", datetime.now(timezone.utc), {})

    call = runs_collection(storage).update_one.call_args
    assert call.kwargs.get("upsert", False) is False


def test_finish_run_computes_duration_in_seconds(storage):
    started_at = datetime.now(timezone.utc) - timedelta(seconds=5)

    storage.finish_run(ObjectId(), "success", started_at, {})

    fields = runs_collection(storage).update_one.call_args.args[1]["$set"]
    assert isinstance(fields["duration_s"], float)
    assert 5 <= fields["duration_s"] < 6


def test_finish_run_records_failure_and_error(storage):
    storage.finish_run(ObjectId(), "failed", datetime.now(timezone.utc), {}, error="HTTPError: 500")

    fields = runs_collection(storage).update_one.call_args.args[1]["$set"]
    assert fields["status"] == "failed"
    assert fields["error"] == "HTTPError: 500"
