import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db


def test_final_runtime_has_only_current_application_set():
    retired = {"wag" + "tail", "model" + "cluster", "tag" + "git", "content", "core"}
    installed_roots = {value.split(".", 1)[0] for value in settings.INSTALLED_APPS}

    assert retired.isdisjoint(installed_roots)
    assert {"publishing", "studio", "accounts", "standards", "resources"} <= installed_roots


def test_retired_routes_are_gone_without_catching_current_public_urls(client):
    assert client.get("/legacy-cms/").status_code == 404
    assert client.get("/documents/").status_code == 404
    assert client.get("/articles/").status_code == 200
    assert client.get("/healthz/").json()["status"] == "ok"
