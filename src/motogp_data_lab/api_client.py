#api_client.py: comunicação HTTP e tratamento de erros.
import logging
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logger = logging.getLogger(__name__)

BASE_URL = "https://api.motogp.pulselive.com/motogp/v1"
MIN_REQUEST_INTERVAL = 0.2
_last_request_time = 0.0

def _throttle():
    global _last_request_time

    elapsed = time.monotonic() - _last_request_time
    wait = MIN_REQUEST_INTERVAL - elapsed
    if wait > 0:
        time.sleep(wait)

    _last_request_time = time.monotonic()

def _build_session():
    http_session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )

    http_session.mount("https://", HTTPAdapter(max_retries=retries))
    return http_session

_http_session = _build_session()

def get_json(path: str, params: dict | None = None):
    url = f"{BASE_URL}/{path.lstrip('/')}"

    try:
        _throttle()
        start = time.perf_counter()
        response = _http_session.get(
            url,
            params=params,
            timeout=20,
        )
        elapsed = time.perf_counter() - start

        logger.info("GET %s -> %s (%.2fs)", response.url, response.status_code, elapsed)

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error("GET %s failed: %s", url, e)
        raise

def get_seasons() -> list[dict]:
    return get_json(
        "results/seasons",
    )

def get_events(season_id: str, is_finished: bool=True) -> list[dict]:
    return get_json(
        "results/events",
        {"seasonUuid": season_id, "isFinished": str(is_finished).lower()},
    )

def get_categories(season_id: str) -> list[dict]:
    return get_json(
        "results/categories",
        {"seasonUuid": season_id},
    )

def get_sessions(event_id: str, category_id: str)  -> list[dict]:
    return get_json(
        "results/sessions",
        {"eventUuid": event_id, "categoryUuid": category_id},
    )

def get_classification(session_id: str) -> dict:
    return get_json(
        f"results/session/{session_id}/classification",
    )

def get_grid(event_id: str, category_id: str)  -> list[dict]:
    return get_json(
        f"results/event/{event_id}/category/{category_id}/grid",
    )

def get_standings(season_id: str, category_id: str) -> dict:
    return get_json(
        "results/standings",
        {"seasonUuid": season_id, "categoryUuid": category_id},
    )