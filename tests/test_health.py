import pytest
from django.urls import reverse
from wagtail.models import Site


@pytest.mark.django_db
def test_homepage_is_the_sdzjoy_wagtail_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "少惰主" in response.content.decode()
    assert response.context["page"].specific_class.__name__ == "HomePage"
    assert Site.objects.get(is_default_site=True).root_page_id == response.context[
        "page"
    ].id


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
