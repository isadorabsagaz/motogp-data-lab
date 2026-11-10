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

    Por padrão não há sessões, grid nem standings: só o upsert de "events" tem dados.
    Cada teste pode mudar o return_value de qualquer mock.
    """
    with patch(f"{INGESTION}.get_seasons", return_value=FAKE_SEASONS), \
         patch(f"{INGESTION}.get_categories", return_value=FAKE_CATEGORIES), \
         patch(f"{INGESTION}.get_events", return_value=FAKE_EVENTS) as mock_events, \
         patch(f"{INGESTION}.get_sessions", return_value=[]) as mock_sessions, \
         patch(f"{INGESTION}.get_classification", return_value={"classification": []}) as mock_classification, \
         patch(f"{INGESTION}.get_grid", return_value=[]) as mock_grid, \
         patch(f"{INGESTION}.get_standings", return_value={"classification": []}) as mock_standings:
        yield {
            "events": mock_events,
            "sessions": mock_sessions,
            "classification": mock_classification,
            "grid": mock_grid,
            "standings": mock_standings,
        }


def upserted(storage, collection):
    """Devolve as listas de documentos enviadas ao upsert_many para uma coleção."""
    return [
        c.args[1]
        for c in storage.upsert_many.call_args_list
        if c.args[0] == collection
    ]


def make_storage(already_collected=()):
    """Storage falso. `already_collected` = ids das sessões que já têm classificação no banco.

    Sem configurar o has_classification, o MagicMock devolveria outro MagicMock,
    que é truthy: toda sessão pareceria já coletada.
    """
    storage = MagicMock()
    storage.has_classification.side_effect = lambda session_id: session_id in already_collected
    return storage


def test_collect_season_ignores_test_events(fake_api):
    storage = make_storage()

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP")

    fake_api["events"].assert_called_once_with("S2025")
    assert upserted(storage, "events") == [FAKE_EVENTS[:2]]
    # Sessões pedidas só para os GPs, com o UUID da categoria resolvido
    assert fake_api["sessions"].call_count == 2
    fake_api["sessions"].assert_any_call(event_id="E-THA", category_id="C-GP")
    fake_api["sessions"].assert_any_call(event_id="E-ARG", category_id="C-GP")


def test_collect_season_filters_by_event_short(fake_api):
    storage = make_storage()

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="THA")

    assert upserted(storage, "events") == [[FAKE_EVENTS[0]]]
    fake_api["sessions"].assert_called_once_with(event_id="E-THA", category_id="C-GP")


def test_collect_season_no_events_logs_warning_and_stops(fake_api, caplog):
    storage = make_storage()

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="XXX")

    storage.upsert_many.assert_not_called()
    fake_api["sessions"].assert_not_called()
    assert "No events found" in caplog.text


def test_collect_season_enriches_classification(fake_api):
    storage = make_storage()
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


# ---------- retomada (--force) ----------

TWO_SESSIONS = [{"id": "SES-FP1", "type": "FP"}, {"id": "SES-RAC", "type": "RAC"}]


def test_collect_season_skips_only_sessions_already_collected(fake_api):
    storage = make_storage(already_collected={"SES-FP1"})
    fake_api["sessions"].return_value = TWO_SESSIONS

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="THA")

    storage.has_classification.assert_any_call("SES-FP1")
    storage.has_classification.assert_any_call("SES-RAC")
    # Só a sessão que ainda não está no banco vai à API
    fake_api["classification"].assert_called_once_with(session_id="SES-RAC")


def test_collect_season_collects_everything_when_db_is_empty(fake_api):
    storage = make_storage()
    fake_api["sessions"].return_value = TWO_SESSIONS

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="THA")

    assert fake_api["classification"].call_count == 2


def test_collect_season_skips_when_all_collected(fake_api, caplog):
    storage = make_storage(already_collected={"SES-FP1", "SES-RAC"})
    fake_api["sessions"].return_value = TWO_SESSIONS

    with caplog.at_level("INFO"):
        ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="THA")

    fake_api["classification"].assert_not_called()
    assert upserted(storage, "classification") == []
    # Eventos e sessões continuam sendo atualizados
    assert upserted(storage, "sessions") == [TWO_SESSIONS]
    assert "Skipped 2 sessions" in caplog.text


def test_collect_season_force_recollects_existing_sessions(fake_api):
    storage = make_storage(already_collected={"SES-FP1", "SES-RAC"})
    fake_api["sessions"].return_value = TWO_SESSIONS

    ingestion.collect_season(
        storage, season_year=2025, category_name="MotoGP", event_short="THA", force=True
    )

    assert fake_api["classification"].call_count == 2
    fake_api["classification"].assert_any_call(session_id="SES-FP1")
    fake_api["classification"].assert_any_call(session_id="SES-RAC")


# ---------- grid ----------

FAKE_GRID = [
    {"qualifying_position": 1, "rider": {"id": "R1"}},
    {"qualifying_position": 2, "rider": {"id": "R2"}},
]


def test_collect_season_grid_once_per_event_not_per_session(fake_api):
    storage = make_storage()
    fake_api["sessions"].return_value = TWO_SESSIONS
    fake_api["grid"].return_value = FAKE_GRID

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP")

    # 2 GPs (o teste BCN é ignorado), cada um com 2 sessões: o grid é por evento
    assert fake_api["grid"].call_count == 2
    fake_api["grid"].assert_any_call(event_id="E-THA", category_id="C-GP")
    fake_api["grid"].assert_any_call(event_id="E-ARG", category_id="C-GP")
    # Um único upsert por evento, já com a lista completa
    assert len(upserted(storage, "grid")) == 2
    assert all(len(docs) == 2 for docs in upserted(storage, "grid"))


def test_collect_season_enriches_grid_with_composite_id(fake_api):
    storage = make_storage()
    fake_api["grid"].return_value = FAKE_GRID[:1]

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="THA")

    assert upserted(storage, "grid") == [[{
        "qualifying_position": 1,
        "rider": {"id": "R1"},
        "event_id": "E-THA",
        "season_year": 2025,
        "category_id": "C-GP",
        "rider_id": "R1",
        "id": "E-THA:C-GP:R1",
    }]]


def test_collect_season_collects_grid_even_when_sessions_skipped(fake_api):
    storage = make_storage(already_collected={"SES-FP1", "SES-RAC"})
    fake_api["sessions"].return_value = TWO_SESSIONS
    fake_api["grid"].return_value = FAKE_GRID

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="THA")

    fake_api["classification"].assert_not_called()
    fake_api["grid"].assert_called_once_with(event_id="E-THA", category_id="C-GP")


# ---------- standings ----------

FAKE_STANDINGS = {
    "file": "worldstanding.pdf",
    "classification": [
        {"id": "ST1", "position": 1, "points": 545, "rider": {"id": "R1"}},
        {"id": "ST2", "position": 2, "points": 467, "rider": {"id": "R2"}},
    ],
}


def test_collect_season_standings_once_per_run(fake_api):
    storage = make_storage()
    fake_api["grid"].return_value = FAKE_GRID

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP")

    # 2 eventos, mas o standings é da temporada: uma requisição só
    fake_api["standings"].assert_called_once_with(season_id="S2025", category_id="C-GP")
    assert len(upserted(storage, "standings")) == 1


def test_collect_season_enriches_standings(fake_api):
    storage = make_storage()
    fake_api["grid"].return_value = [{"qualifying_position": 1, "rider": {"id": "R-GRID"}}]
    fake_api["standings"].return_value = FAKE_STANDINGS

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="THA")

    # rider_id vem do próprio item do standings (não de uma variável do grid)
    assert upserted(storage, "standings") == [[
        {"id": "ST1", "position": 1, "points": 545, "rider": {"id": "R1"},
         "season_year": 2025, "category_id": "C-GP", "rider_id": "R1"},
        {"id": "ST2", "position": 2, "points": 467, "rider": {"id": "R2"},
         "season_year": 2025, "category_id": "C-GP", "rider_id": "R2"},
    ]]


def test_collect_season_standings_without_grid_does_not_crash(fake_api):
    storage = make_storage()
    fake_api["standings"].return_value = FAKE_STANDINGS

    ingestion.collect_season(storage, season_year=2025, category_name="MotoGP", event_short="THA")

    assert len(upserted(storage, "standings")[0]) == 2
