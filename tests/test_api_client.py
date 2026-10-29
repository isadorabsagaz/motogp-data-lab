import logging
from unittest.mock import MagicMock, patch

import pytest
import requests
from urllib3.util import Retry

from src.motogp_data_lab import api_client

def test_get_json_success():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.url = "https://fake/results/seasons"
    fake_response.json.return_value = [{"id": "abc", "year": 2025}]

    with patch.object(api_client._http_session, "get", return_value=fake_response) as mock_get:
        result = api_client.get_json("results/seasons")

    assert result == [{"id": "abc", "year": 2025}]
    mock_get.assert_called_once()

def test_get_json_http_500_raises(caplog):
    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.url = "https://fake/results/seasons"
    fake_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")

    with patch.object(api_client._http_session, "get", return_value=fake_response) as mock_get:
        with pytest.raises(requests.exceptions.HTTPError):
            api_client.get_json("results/seasons")

    mock_get.assert_called_once()
    fake_response.json.assert_not_called()
    assert any(r.levelno == logging.ERROR for r in caplog.records)

def test_get_json_timeout_raises(caplog):
    with patch.object(api_client._http_session, "get", side_effect=requests.exceptions.Timeout("read timed out")) as mock_get:
        with pytest.raises(requests.exceptions.Timeout):
            api_client.get_json("results/seasons")

    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["timeout"] == 20
    assert "results/seasons" in caplog.text

def test_http_session_retry_config():
    adapter = api_client._http_session.get_adapter(api_client.BASE_URL)
    retry = adapter.max_retries

    assert isinstance(retry, Retry)
    assert retry.total == 3
    assert retry.backoff_factor == 1
    assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
    assert "GET" in retry.allowed_methods
    assert retry.raise_on_status is False

@pytest.mark.parametrize(
    "func, kwargs, expected_args",
    [
        (api_client.get_seasons, {}, ("results/seasons",)),
        (api_client.get_events, {"season_id": "S1"}, ("results/events", {"seasonUuid": "S1", "isFinished": "true"})),
        (api_client.get_events, {"season_id": "S1", "is_finished": False}, ("results/events", {"seasonUuid": "S1", "isFinished": "false"})),
        (api_client.get_categories, {"season_id": "S1"}, ("results/categories", {"seasonUuid": "S1"})),
        (api_client.get_sessions, {"event_id": "E1", "category_id": "C1"}, ("results/sessions", {"eventUuid": "E1", "categoryUuid": "C1"})),
        (api_client.get_classification, {"session_id": "X1"}, ("results/session/X1/classification",)),
        (api_client.get_grid, {"event_id": "E1", "category_id": "C1"}, ("results/event/E1/category/C1/grid",)),
        (api_client.get_standings, {"season_id": "S1", "category_id": "C1"}, ("results/standings", {"seasonUuid": "S1", "categoryUuid": "C1"})),
    ],
    ids=["seasons", "events", "events_not_finished", "categories", "sessions", "classification", "grid", "standings"],
)
def test_endpoint_calls_get_json(func, kwargs, expected_args):
    with patch.object(api_client, "get_json", return_value="fake") as mock_get_json:
        result = func(**kwargs)

    mock_get_json.assert_called_once_with(*expected_args)
    assert result == "fake"
