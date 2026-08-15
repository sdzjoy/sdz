import pytest
from django.test import RequestFactory
from django.views.defaults import server_error


@pytest.mark.django_db
def test_not_found_uses_the_site_error_page(client):
    response = client.get("/this-page-does-not-exist/")

    assert response.status_code == 404
    assert "页面没有找到" in response.content.decode()


def test_server_error_uses_the_site_error_page():
    response = server_error(RequestFactory().get("/failing-request/"))

    assert response.status_code == 500
    assert "服务暂时不可用" in response.content.decode()
