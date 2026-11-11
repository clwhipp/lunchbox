from datetime import date
from unittest.mock import Mock

import pytest
from django.db import DatabaseError
from django.test import Client

from schoolmenu import services, views
from schoolmenu.models import Food, FoodPreference

pytestmark = pytest.mark.django_db
QUERY = {"week": "2026-11-09", "school": "NORTHEAST_ELEMENTARY", "grade": "01"}


@pytest.fixture
def source(monkeypatch, weekly, daily):
    mock = Mock(side_effect=lambda s, kind, d: weekly if kind == "weekly" else daily)
    monkeypatch.setattr(services, "fetch_provider", mock)
    return mock


def test_full_page_and_redirects(client, source):
    response = client.get("/", QUERY)
    assert response.status_code == 200
    assert response.content.count(b'class="day-column"') == 5
    assert b"Cheese Pizzable" in response.content and b"No menu published" in response.content
    assert b"Vegetables" in response.content and b"Drinks" in response.content
    assert b"Condiments" not in response.content
    assert b"SACK LUNCHES" in response.content
    assert b"LUNCH FROM HOME" not in response.content
    assert b"SCHOOL LUNCH POTENTIALLY" not in response.content
    assert b"Needs a look" not in response.content
    assert response.context["sack_lunch_days"] == []
    response = client.get("/", QUERY | {"week": "2026-11-11"})
    assert response.status_code == 302 and "week=2026-11-09" in response.url
    response = client.get("/", {"date": "2026-11-11"})
    assert response.status_code == 302 and "week=2026-11-09" in response.url
    assert client.get("/", {"week": "invalid"}).status_code == 400
    assert client.post("/").status_code == 400


def test_extra_groups_are_expanded_by_default(client, source):
    response = client.get("/", QUERY)
    details = response.content.count(b'<details class="extra-groups"')
    expanded = response.content.count(b'<details class="extra-groups" open>')

    assert details > 0
    assert expanded == details


@pytest.mark.parametrize("grade", ["01", "02", "03", "04", "05"])
def test_grade_selector_supports_grades_one_through_five(client, source, grade):
    response = client.get("/", QUERY | {"grade": grade})

    assert response.status_code == 200
    assert response.context["selection"].grade == grade
    assert response.context["grades"] == ["01", "02", "03", "04", "05"]


def test_default_page_uses_current_week(client, source, monkeypatch):
    monkeypatch.setattr(services.timezone, "localdate", lambda: date(2026, 11, 11))
    response = client.get("/")
    assert response.status_code == 200
    assert source.call_args.args[2] == date(2026, 11, 9)


@pytest.mark.parametrize("day", [7, 8])
def test_weekend_default_and_shortcut(client, source, monkeypatch, day):
    monkeypatch.setattr(services.timezone, "localdate", lambda: date(2026, 11, day))
    response = client.get("/")
    assert response.context["selection"].start == date(2026, 11, 9)
    assert source.call_args.args[2] == date(2026, 11, 9)
    assert "week=2026-11-09" in response.context["current_url"]
    assert response.context["current_label"] == "Upcoming week"
    explicit = client.get("/", QUERY | {"week": "2026-11-02"})
    assert explicit.context["selection"].start == date(2026, 11, 2)


def test_preferences_fragments_redirects_and_validation(client, source):
    client.get("/", QUERY)
    food = Food.objects.get(source_id=43863)
    url = f"/foods/{food.pk}/preference/"
    response = client.post(url, QUERY | {"state": "liked"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert response.content.count(f'data-food-id="{food.pk}" data-preference="liked"'.encode()) == 2
    assert b"<!doctype" not in response.content
    assert source.call_count == 1
    assert client.post(url, QUERY | {"state": "disliked"}).status_code == 302
    assert (
        FoodPreference.objects.get(profile=services.default_profile(), pe_id=food.pe_id).value
        == "disliked"
    )
    assert client.post(url, QUERY | {"state": "neutral"}).status_code == 302
    assert not FoodPreference.objects.exists()
    assert client.post(url, QUERY | {"state": "both"}).status_code == 400
    assert client.post(url, QUERY | {"grade": "invalid"}).status_code == 400
    assert client.post(url, QUERY | {"school": "ABBIE_GROVE", "state": "liked"}).status_code == 404
    assert client.get(url).status_code == 405


def test_csrf_enforced_and_failed_write(client, source, monkeypatch):
    client.get("/", QUERY)
    food = Food.objects.first()
    url = f"/foods/{food.pk}/preference/"
    assert Client(enforce_csrf_checks=True).post(url, QUERY | {"state": "liked"}).status_code == 403
    monkeypatch.setattr(services, "save_preference", Mock(side_effect=DatabaseError("locked")))
    assert client.post(url, QUERY | {"state": "liked"}).status_code == 503
    assert not FoodPreference.objects.exists()


def test_detail_full_and_fragment(client, source):
    client.get("/", QUERY)
    food = Food.objects.get(source_id=182511)
    params = QUERY | {"serving_date": "2026-11-09"}
    url = f"/foods/{food.pk}/"
    response = client.get(url, params)
    assert response.status_code == 200
    assert b"674.63" in response.content and b"10.12" in response.content
    assert b"Contains Milk, Wheat. May contain Soy." in response.content
    assert b"Cheese Blend" in response.content
    response = client.get(url, params, HTTP_HX_REQUEST="true")
    assert response.status_code == 200 and b"<!doctype" not in response.content
    assert source.call_count == 2
    assert client.get(url, params | {"serving_date": "bad"}).status_code == 404
    assert client.get(url, params | {"serving_date": "2026-11-11"}).status_code == 404
    assert client.get(url, params | {"grade": "bad"}).status_code == 400
    assert client.get("/foods/999999/", params).status_code == 404


def test_upstream_text_is_escaped(client, weekly, monkeypatch):
    weekly["11/9/2026"]["ENTREES"][0]["MenuItemDescription"] = "<script>alert(1)</script>"
    monkeypatch.setattr(services, "fetch_provider", Mock(return_value=weekly))
    response = client.get("/", QUERY)
    assert b"<script>alert(1)</script>" not in response.content
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in response.content


def test_readiness_and_liveness(client, monkeypatch):
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    executor = Mock()
    executor.migration_plan.return_value = ["pending"]
    monkeypatch.setattr(views, "MigrationExecutor", Mock(return_value=executor))
    assert client.get("/health/ready").status_code == 503
    monkeypatch.setattr(views, "MigrationExecutor", Mock(side_effect=DatabaseError("offline")))
    assert client.get("/health/ready").json() == {"status": "database unavailable"}


def test_thumbnail_binary_response_and_fallback(client, source, monkeypatch):
    client.get("/", QUERY)
    food = Food.objects.first()
    fetch = Mock(return_value=(b"jpeg bytes", "image/jpeg"))
    monkeypatch.setattr(views, "thumbnail_bytes", fetch)
    url = f"/foods/{food.pk}/thumbnail/"
    response = client.get(url)
    assert response.content == b"jpeg bytes" and response["Content-Type"] == "image/jpeg"
    assert response["Cache-Control"] == "public, max-age=3600"
    assert fetch.call_args.args[0] == food.pe_id
    fetch.return_value = None
    response = client.get(url)
    assert response.status_code == 302 and response.url.endswith("menus/plate.svg")
    assert client.get("/foods/999999/thumbnail/").status_code == 404
    assert client.post(url).status_code == 405
