import requests
from django.conf import settings

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(token):
    if not settings.TURNSTILE_REQUIRED:
        return True
    if not token or not settings.TURNSTILE_SECRET_KEY:
        return False

    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={
                "secret": settings.TURNSTILE_SECRET_KEY,
                "response": token,
            },
            timeout=5,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError):
        return False

    if not result.get("success") or result.get("action") not in (None, "signup"):
        return False
    expected_hostnames = settings.TURNSTILE_EXPECTED_HOSTNAMES
    return not expected_hostnames or result.get("hostname") in expected_hostnames
