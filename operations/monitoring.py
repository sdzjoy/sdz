import time
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit

from django.conf import settings
from django.utils import timezone

from .models import AlertIncident, MonitorCheck


def _severity_for(url):
    path = urlsplit(url).path
    if path in {"/", "/account/login/"} or "hvac." in url:
        return MonitorCheck.Severity.CRITICAL
    if path.startswith(("/search/", "/standards/")):
        return MonitorCheck.Severity.HIGH
    return MonitorCheck.Severity.MEDIUM


def _classify_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return "http_error"
    if isinstance(exc, urllib.error.URLError):
        reason = str(exc.reason).lower()
        if "timed out" in reason:
            return "timeout"
        if "name" in reason or "resolve" in reason:
            return "dns"
        return "connection"
    return type(exc).__name__.lower()[:80]


def check_url(url, *, timeout=8):
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("监控地址只允许 HTTP(S)。")
    severity = _severity_for(url)
    started = time.monotonic()
    status_code = None
    error_kind = ""
    try:
        request = urllib.request.Request(  # noqa: S310 - scheme allowlisted above
            url, headers={"User-Agent": "SDZJOY-Monitor/1.0"}
        )
        with urllib.request.urlopen(  # noqa: S310 - scheme allowlisted above
            request, timeout=timeout
        ) as response:
            status_code = response.status
            ok = 200 <= status_code < 400
    except Exception as exc:
        ok = False
        status_code = getattr(exc, "code", None)
        error_kind = _classify_error(exc)
    latency_ms = int((time.monotonic() - started) * 1000)
    check = MonitorCheck.objects.create(
        name=urlsplit(url).path or urlsplit(url).netloc,
        url=url,
        severity=severity,
        ok=ok,
        status_code=status_code,
        latency_ms=latency_ms,
        error_kind=error_kind,
    )
    key = f"critical-path:{url}"[:200]
    if ok:
        AlertIncident.objects.filter(key=key, status=AlertIncident.Status.OPEN).update(
            status=AlertIncident.Status.RECOVERED, recovered_at=timezone.now()
        )
    else:
        AlertIncident.objects.update_or_create(
            key=key,
            defaults={
                "title": f"关键路径异常：{urlsplit(url).path or url}",
                "severity": severity,
                "status": AlertIncident.Status.OPEN,
                "recovered_at": None,
            },
        )
    return check


def run_checks():
    origin = settings.PUBLIC_SITE_ORIGIN.rstrip("/") + "/"
    results = []
    for configured in settings.CRITICAL_PATH_URLS:
        url = (
            configured
            if configured.startswith(("http://", "https://"))
            else urljoin(origin, configured.lstrip("/"))
        )
        results.append(check_url(url))
    return results
