from django.db import connection
from django.http import JsonResponse


def healthz(request):
    return JsonResponse({"status": "ok", "service": "sdzjoy-platform"})


def readyz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse(
            {"status": "unavailable", "service": "sdzjoy-platform"}, status=503
        )
    return JsonResponse({"status": "ready", "service": "sdzjoy-platform"})
