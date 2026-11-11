import argparse
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId

from src.motogp_data_lab import main as main_module

MAIN = "src.motogp_data_lab.main"

ARGS = argparse.Namespace(season=2025, category="MotoGP", event="THA", force=False)
RUN_ID = ObjectId()
STARTED_AT = datetime(2026, 11, 10, tzinfo=timezone.utc)


@pytest.fixture
def storage():
    s = MagicMock()
    s.start_run.return_value = (RUN_ID, STARTED_AT)
    with patch(f"{MAIN}.MongoStorage", return_value=s), \
         patch(f"{MAIN}.parse_args", return_value=ARGS), \
         patch(f"{MAIN}.get_stats", return_value={"requests": 5, "failed_requests": 0}):
        yield s


def test_main_success_finishes_run_with_stats(storage):
    with patch(f"{MAIN}.collect_season", return_value={"sessions_skipped": 3}):
        main_module.main()

    storage.start_run.assert_called_once_with(vars(ARGS))
    storage.finish_run.assert_called_once_with(
        run_id=RUN_ID, status="success", started_at=STARTED_AT,
        stats={"sessions_skipped": 3, "api": {"requests": 5, "failed_requests": 0}},
    )
    storage.close.assert_called_once()


def test_main_failure_finishes_run_as_failed_and_reraises(storage):
    with patch(f"{MAIN}.collect_season", side_effect=ValueError("Season 1900 not found")):
        with pytest.raises(ValueError):
            main_module.main()

    kwargs = storage.finish_run.call_args.kwargs
    assert kwargs["status"] == "failed"
    assert kwargs["error"] == "ValueError: Season 1900 not found"
    assert kwargs["stats"] == {"api": {"requests": 5, "failed_requests": 0}}
    storage.close.assert_called_once()


def test_main_mongo_down_does_not_start_run(storage):
    # Sem Mongo não há onde gravar o run: o erro sobe direto e a conexão é fechada.
    storage.ping.side_effect = ConnectionError("mongo down")

    with pytest.raises(ConnectionError):
        main_module.main()

    storage.start_run.assert_not_called()
    storage.finish_run.assert_not_called()
    storage.close.assert_called_once()
