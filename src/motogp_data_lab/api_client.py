#api_client.py: comunicação HTTP e tratamento de erros.
import requests

BASE_URL = "https://api.motogp.pulselive.com/motogp/v1"

def get_json(path: str, params: dict | None = None):
    url = f"{BASE_URL}/{path.lstrip('/')}"

    response = requests.get(
        url,
        params=params,
        timeout=20,
    )

    response.raise_for_status()
    return response.json()