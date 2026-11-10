from datetime import date
from unittest.mock import Mock

import pytest
from django.db import DatabaseError
from django.test import Client
from django.urls import reverse

from schoolmenu import services
from schoolmenu.models import Food, FoodPreference, SackLunch

pytestmark = pytest.mark.django_db
QUERY = {"week": "2026-11-09", "school": "NORTHEAST_ELEMENTARY", "grade": "01"}


@pytest.fixture
def source(monkeypatch, weekly, daily):
    mock = Mock(side_effect=lambda s, kind, d: weekly if kind == "weekly" else daily)
    monkeypatch.setattr(services, "fetch_provider", mock)
    return mock


def test_week_shows_explicit_sack_lunch_controls_instead_of_liking_statuses(client, source):
    response = client.get("/", QUERY)

    assert response.status_code == 200
    assert response.content.count(b'aria-label="Sack lunch for ') == 5
    assert response.content.count(b'type="checkbox" name="confirmed"') == 5
    assert b"SACK LUNCHES" in response.content
    assert b"No sack lunches confirmed." in response.content
    for removed in [
        b"LUNCH FROM HOME",
        b"NEEDS A LOOK",
        b"SCHOOL LUNCH POTENTIALLY",
        b"Lunch from home likely",
        b"Needs review",
        b"School lunch potentially",
    ]:
        assert removed not in response.content


def test_checking_a_day_persists_and_summary_lists_only_confirmed_dates(client, source):
    client.get("/", QUERY)
    response = client.post(
        reverse("sack_lunch"),
        QUERY | {"serving_date": "2026-11-10", "confirmed": "true"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert b"<!doctype" not in response.content
    row = SackLunch.objects.get()
    assert row.profile == services.default_profile()
    assert str(row.school_id) == services.Selection.parse(QUERY).school.value
    assert row.week_start == date(2026, 11, 9)
    assert row.serving_date == date(2026, 11, 10)
    assert b"1<small> day" in response.content
    assert b"Tue, Nov 10" in response.content
    assert b'aria-label="Sack lunch for Tuesday, November 10"' in response.content
    assert response.content.count(b'type="checkbox" name="confirmed"') == 5

    page = client.get("/", QUERY)
    assert page.context["days"][1].sack_lunch is True
    assert page.context["sack_lunch_days"] == [page.context["days"][1]]
    assert page.context["days"][0].sack_lunch is False
    assert b"Tue, Nov 10" in page.content
    assert b"Mon, Nov 9" not in page.content

    response = client.post(
        reverse("sack_lunch"),
        QUERY | {"serving_date": "2026-11-10", "confirmed": "false"},
    )
    assert response.status_code == 302
    assert not SackLunch.objects.exists()
    page = client.get("/", QUERY)
    assert page.context["sack_lunch_days"] == []
    assert b"No sack lunches confirmed." in page.content


def test_sack_lunch_is_scoped_by_school_and_exact_date_not_grade(client, source):
    url = reverse("sack_lunch")
    client.post(url, QUERY | {"serving_date": "2026-11-09", "confirmed": "true"})
    other_grade = QUERY | {"grade": "02"}
    page = client.get("/", other_grade)
    assert [day.date for day in page.context["sack_lunch_days"]] == [date(2026, 11, 9)]
    assert page.context["days"][0].sack_lunch is True

    client.post(url, other_grade | {"serving_date": "2026-11-12", "confirmed": "true"})
    client.post(
        url,
        {"week": "2026-11-09", "school": "SOUTHEAST_ELEMENTARY", "grade": "01"}
        | {"serving_date": "2026-11-09", "confirmed": "true"},
    )

    assert SackLunch.objects.count() == 3
    page = client.get("/", QUERY)
    assert [day.date for day in page.context["sack_lunch_days"]] == [
        date(2026, 11, 9),
        date(2026, 11, 12),
    ]
    assert (
        SackLunch.objects.filter(
            school_id=services.Selection.parse(QUERY).school.value,
        ).count()
        == 2
    )

    client.post(url, other_grade | {"serving_date": "2026-11-09", "confirmed": "false"})
    page = client.get("/", QUERY)
    assert [day.date for day in page.context["sack_lunch_days"]] == [date(2026, 11, 12)]

    other_school = client.get(
        "/", {"week": "2026-11-09", "school": "SOUTHEAST_ELEMENTARY", "grade": "01"}
    )
    assert [day.date for day in other_school.context["sack_lunch_days"]] == [date(2026, 11, 9)]


def test_confirmed_non_menu_day_is_listed(client, source):
    response = client.post(
        reverse("sack_lunch"),
        QUERY | {"serving_date": "2026-11-11", "confirmed": "on"},
    )

    assert response.status_code == 302
    page = client.get("/", QUERY)
    assert page.context["days"][2].items == []
    assert page.context["days"][2].sack_lunch is True
    assert page.context["sack_lunch_days"] == [page.context["days"][2]]
    assert b"Wed, Nov 11" in page.content


@pytest.mark.parametrize("serving_date", ["", "bad", "2026-11-07", "2026-11-08", "2026-11-16"])
def test_invalid_dates_are_rejected(client, source, serving_date):
    response = client.post(
        reverse("sack_lunch"),
        QUERY | {"serving_date": serving_date, "confirmed": "true"},
    )

    assert response.status_code == 400
    assert not SackLunch.objects.exists()


def test_invalid_confirmed_and_selection_are_rejected(client, source):
    url = reverse("sack_lunch")
    assert (
        client.post(url, QUERY | {"serving_date": "2026-11-09", "confirmed": "maybe"}).status_code
        == 400
    )
    assert (
        client.post(
            url,
            {"week": "2026-11-09", "school": "bad", "grade": "01"}
            | {"serving_date": "2026-11-09", "confirmed": "true"},
        ).status_code
        == 400
    )
    assert client.get(url, QUERY | {"serving_date": "2026-11-09"}).status_code == 405
    assert not SackLunch.objects.exists()


def test_csrf_and_database_failure_restore_safe_state(client, source, monkeypatch):
    url = reverse("sack_lunch")
    payload = QUERY | {"serving_date": "2026-11-09", "confirmed": "true"}
    assert Client(enforce_csrf_checks=True).post(url, payload).status_code == 403
    monkeypatch.setattr(services, "save_sack_lunch", Mock(side_effect=DatabaseError("locked")))
    response = client.post(url, payload, HTTP_HX_REQUEST="true")
    assert response.status_code == 503
    assert b"Could not save" in response.content
    assert not SackLunch.objects.exists()


def test_likes_and_dislikes_do_not_create_sack_lunch_entries(client, source):
    page = client.get("/", QUERY)
    food = Food.objects.get(pk=page.context["days"][0].entrees[0].food_id)
    services.save_preference(food, "disliked")
    chicken = Food.objects.get(source_id=43863)
    services.save_preference(chicken, "liked")

    page = client.get("/", QUERY)

    assert FoodPreference.objects.count() == 2
    assert page.context["sack_lunch_days"] == []
    assert b"No sack lunches confirmed." in page.content
