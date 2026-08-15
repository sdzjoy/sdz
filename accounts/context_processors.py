from django.conf import settings


def security_settings(request):
    return {
        "TURNSTILE_REQUIRED": settings.TURNSTILE_REQUIRED,
        "TURNSTILE_SITE_KEY": settings.TURNSTILE_SITE_KEY,
    }
