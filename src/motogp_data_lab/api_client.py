#api_client.py: comunicação HTTP e tratamento de erros.
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

BASE_URL = "https://api.motogp.pulselive.com/motogp/v1"

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

    response = _http_session.get(
        url,
        params=params,
        timeout=20,
    )

    response.raise_for_status()
    return response.json()