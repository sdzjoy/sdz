from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import override_settings

from operations.models import AlertIncident
from operations.monitoring import check_url

pytestmark = pytest.mark.django_db


class Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@override_settings(PUBLIC_SITE_ORIGIN="https://sdzjoy.example")
def test_monitor_classifies_failure_and_records_recovery():
    with patch("urllib.request.urlopen", side_effect=OSError("network down")):
        failed = check_url("https://sdzjoy.example/")
    assert not failed.ok
    incident = AlertIncident.objects.get()
    assert incident.severity == "critical"
    assert incident.status == "open"

    with patch("urllib.request.urlopen", return_value=Response()):
        recovered = check_url("https://sdzjoy.example/")
    incident.refresh_from_db()
    assert recovered.ok
    assert incident.status == "recovered"


def test_production_compose_keeps_database_private_and_limits_logs():
    root = Path(__file__).resolve().parents[1]
    compose = (root / "compose.production.yml").read_text(encoding="utf-8")
    db_section = compose.split("  db:", 1)[1].split("\n  web:", 1)[0]
    assert "ports:" not in db_section
    assert 'expose:\n      - "5432"' in db_section
    assert "mem_limit:" in compose
    assert "max-size: 10m" in compose
    assert '"127.0.0.1:${SDZJOY_PORT:-8080}:8080"' in compose


def test_restore_script_refuses_a_production_target():
    root = Path(__file__).resolve().parents[1]
    restore = (root / "ops" / "backup" / "restore.sh").read_text(encoding="utf-8")
    assert 'RESTORE_DB_NAME}" == "${PRODUCTION_DB_NAME' in restore
    assert 'RESTORE_DB_HOST}" != "restore-db' in restore
    assert "sha256sum --check" in restore
