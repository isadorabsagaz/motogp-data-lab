from unittest.mock import MagicMock, patch

import pytest

from src.motogp_data_lab import ingestion

# Patch onde a função é USADA (ingestion), não onde é definida (api_client):
# o ingestion importou as funções com "from ... import", então tem referências próprias.
INGESTION = "src.motogp_data_lab.ingestion"

FAKE_SEASONS = [
    {"id": "S2024", "year": 2024, "current": False},
    {"id": "S2025", "year": 2025, "current": False},
]

FAKE_CATEGORIES = [
    {"id": "C-GP", "name": "MotoGP™"},
    {"id": "C-M2", "name": "Moto2™"},
    {"id": "C-M3", "name": "Moto3™"},
]

FAKE_EVENTS = [
    {"id": "E-THA", "short_name": "THA", "test": False},
    {"id": "E-ARG", "short_name": "ARG", "test": False},
    {"id": "E-BCN", "short_name": "BCN", "test": True},
]


# ---------- resolve_season_id ----------

def test_resolve_season_id_found():
    with patch(f"{INGESTION}.get_seasons", return_value=FAKE_SEASONS):
        assert ingestion.resolve_season_id(2025) == "S2025"


def test_resolve_season_id_not_found_raises():
    with patch(f"{INGESTION}.get_seasons", return_value=FAKE_SEASONS):
        with pytest.raises(ValueError, match="1900"):
            ingestion.resolve_season_id(1900)


# ---------- resolve_category_id ----------

@pytest.mark.parametrize(
    "name, expected_id",
    [
        ("MotoGP", "C-GP"),
        ("motogp", "C-GP"),
        ("MotoGP™", "C-GP"),
        ("Moto2", "C-M2"),
    ],
    ids=["exact_without_tm", "lowercase", "with_tm", "other_category"],
)
def test_resolve_category_id_found(name, expected_id):
    with patch(f"{INGESTION}.get_categories", return_value=FAKE_CATEGORIES) as mock_get_categories:
        assert ingestion.resolve_category_id("S2025", name) == expected_id

    mock_get_categories.assert_called_once_with("S2025")


def test_resolve_category_id_not_found_raises():
    with patch(f"{INGESTION}.get_categories", return_value=FAKE_CATEGORIES):
        with pytest.raises(ValueError):
            ingestion.resolve_category_id("S2025", "MotoE")


# ---------- collect_season ----------

@pytest.fixture
def fake_api():
    """Substitui todas as chamadas à API usadas pelo collect_season.

    Por padrão não há sessões, então só o upsert de "events" acontece.
    Cada teste pode mudar o return_value de qualquer mock.
    """
    with patch(f"{INGESTION}.get_seasons", return_value=FAKE_SEASONS), \
         patch(f"{INGESTION}.get_categories", return_value=FAKE_CATEGORIES), \
         patch(f"{INGESTION}.get_events", return_value=FAKE_EVENTS) as mock_events, \
         patch(f"{INGESTION}.get_sessions", return_value=[]) as mock_sessions, \
         patch(f"{INGESTION}.get_classification", return_value={"classification": []}) as mock_classification:
        yield {
            "events": mock_events,
            "sessions": mock_sessions,
            "classification": mock_classification,
        }


def upserted(storage, collection):
    """Devolve as listas de documentos enviadas ao upsert_many para uma coleção."""
    return [
        c.args[1]
        for c in storage.upsert_many.call_args_list
        if c.args[0] == collection
    ]


def test_collect_season_ignores_test_events(fake_api):
    storage = MagicMock()

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP")

    fake_api["events"].assert_called_once_with("S2025")
    assert upserted(storage, "events") == [FAKE_EVENTS[:2]]
    # Sessões pedidas só para os GPs, com o UUID da categoria resolvido
    assert fake_api["sessions"].call_count == 2
    fake_api["sessions"].assert_any_call(event_id="E-THA", category_id="C-GP")
    fake_api["sessions"].assert_any_call(event_id="E-ARG", category_id="C-GP")


def test_collect_season_filters_by_event_short(fake_api):
    storage = MagicMock()

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="THA")

    assert upserted(storage, "events") == [[FAKE_EVENTS[0]]]
    fake_api["sessions"].assert_called_once_with(event_id="E-THA", category_id="C-GP")


def test_collect_season_no_events_logs_warning_and_stops(fake_api, caplog):
    storage = MagicMock()

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="XXX")

    storage.upsert_many.assert_not_called()
    fake_api["sessions"].assert_not_called()
    assert "No events found" in caplog.text


def test_collect_season_enriches_classification(fake_api):
    storage = MagicMock()
    fake_api["sessions"].return_value = [{"id": "SES-RAC", "type": "RAC"}]
    fake_api["classification"].return_value = {
        "classification": [{"id": "CL1", "position": 1, "rider": {"id": "R1"}}]
    }

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="THA")

    fake_api["classification"].assert_called_once_with(session_id="SES-RAC")
    assert upserted(storage, "classification") == [[{
        "id": "CL1",
        "position": 1,
        "rider": {"id": "R1"},
        "session_id": "SES-RAC",
        "event_id": "E-THA",
        "season_year": 2025,
        "category_id": "C-GP",
        "rider_id": "R1",
    }]]
