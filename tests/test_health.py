import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_homepage_is_served_by_the_snapshot_publishing_site(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "少惰主" in response.content.decode()
    assert response.resolver_match.namespace == "publishing"
    assert response.resolver_match.url_name == "home"
    assert response.context["page"].title == "少惰主 · SDZJOY"


@pytest.mark.django_db
def test_health_endpoint_does_not_require_authentication(client):
    response = client.get(reverse("healthz"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "sdzjoy-platform"}


@pytest.mark.django_db
def test_readiness_endpoint_checks_database(client):
    response = client.get(reverse("readyz"))

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "sdzjoy-platform"}
