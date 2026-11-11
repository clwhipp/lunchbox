import hmac
import re
from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock

import pytest
from django.test import RequestFactory, override_settings
from django.urls import reverse

from schoolmenu import calendar_feed, services
from schoolmenu.domain import Day, Group, Item

pytestmark = pytest.mark.django_db


@pytest.fixture
def source(monkeypatch, weekly, daily):
    provider = Mock(
        side_effect=lambda selection, kind, serving_date: weekly if kind == "weekly" else daily
    )
    monkeypatch.setattr(services, "fetch_provider", provider)
    return provider


def empty_week(start):
    return {
        "days": [Day(start + timedelta(days=offset)) for offset in range(5)],
        "stale": False,
        "fetched_at": datetime(2026, 11, 9, 12, tzinfo=UTC),
    }


def test_calendar_token_is_stable_and_bound_to_default_selection():
    first = calendar_feed.calendar_token()
    second = calendar_feed.calendar_token()
    selection = calendar_feed.decode_calendar_token(first)

    assert hmac.compare_digest(first, second)
    assert bool(re.fullmatch(r"[A-Za-z0-9_-]{22}", first))
    assert selection.school.name == "NORTHEAST_ELEMENTARY"
    assert selection.grade == "01"


def test_subscription_url_uses_configured_public_https_base():
    request = RequestFactory().get("/", secure=True, HTTP_HOST="internal:8000")
    with override_settings(CALENDAR_PUBLIC_BASE_URL="https://menus.example.test/lunchbox"):
        url = calendar_feed.calendar_subscription_url(request)

    assert url.startswith("https://menus.example.test/lunchbox/calendar/")
    assert url.endswith(".ics")
    assert "internal" not in url


def test_menu_page_reveals_the_short_default_calendar_url_only_after_post(
    client, source, monkeypatch
):
    monkeypatch.setattr(services.timezone, "localdate", lambda: date(2026, 11, 11))
    page = client.get("/", {"school": "ABBIE_GROVE", "grade": "02"})
    assert page.status_code == 200
    assert b"Subscribe to menu calendar" in page.content
    assert b"Show subscription URL" in page.content
    assert b"calendar-subscription-url" not in page.content
    assert b'<dialog id="calendar-dialog"' in page.content
    assert b"Anyone with this link can view" in page.content

    revealed = client.post(
        "/",
        {
            "school": "ABBIE_GROVE",
            "grade": "02",
            "week": "2026-11-09",
            "calendar_action": "reveal",
        },
    )
    other_revealed = client.post(
        "/",
        {
            "school": "SOUTHEAST_ELEMENTARY",
            "grade": "05",
            "week": "2026-11-09",
            "calendar_action": "reveal",
        },
    )
    assert revealed.status_code == other_revealed.status_code == 200
    first_url = revealed.context["calendar_subscription_url"]
    assert hmac.compare_digest(first_url, other_revealed.context["calendar_subscription_url"])
    assert first_url.startswith("http://testserver/calendar/")
    token = first_url.removeprefix("http://testserver/calendar/").removesuffix(".ics")
    assert bool(re.fullmatch(r"[A-Za-z0-9_-]{22}", token))
    assert "Northeast Elementary" in revealed.content.decode()
    assert "Grade 01" in revealed.content.decode()


def test_calendar_details_have_a_no_javascript_get_fallback(client, source, monkeypatch):
    monkeypatch.setattr(services.timezone, "localdate", lambda: date(2026, 11, 11))
    response = client.get(
        "/",
        {
            "school": "NORTHEAST_ELEMENTARY",
            "grade": "01",
            "week": "2026-11-09",
            "calendar_dialog": "open",
        },
    )

    assert response.status_code == 200
    assert response.context["calendar_dialog_open"] is True
    assert b'<dialog id="calendar-dialog"' in response.content
    assert b"calendar-subscription-url" not in response.content


@override_settings(CALENDAR_PUBLIC_BASE_URL="https://menus.example.test/lunchbox")
def test_calendar_feed_is_private_cached_and_reads_rolling_fourteen_days_without_provider_calls(
    client, monkeypatch
):
    starts = []

    def cached_week(selection, *, fetch=True):
        assert fetch is False
        starts.append(selection.start)
        week = empty_week(selection.start)
        if selection.start == date(2026, 11, 9):
            parent = Item(1, 101, "Cheese, Pizzable", "ENTREES", "", "", "", [], preference="liked")
            choice = Item(
                2,
                102,
                "Fruit Cup",
                "GRAINS",
                "",
                "",
                "",
                [],
                preference="disliked",
                is_related_item=True,
            )
            parent.related_items.append(choice)
            week["days"][2].groups.append(Group("Entrées", "main", [parent, choice]))
        return week

    monkeypatch.setattr(services, "load_week", cached_week)
    monkeypatch.setattr(services.timezone, "localdate", lambda: date(2026, 11, 11))
    provider = Mock(side_effect=AssertionError("the ICS endpoint must not fetch upstream"))
    monkeypatch.setattr(services, "fetch_provider", provider)
    url = reverse("calendar_feed", kwargs={"token": calendar_feed.calendar_token()})

    response = client.get(url)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar; charset=utf-8"
    assert response["Content-Disposition"] == 'inline; filename="lunchbox-menu.ics"'
    assert response["Cache-Control"] == "private, max-age=300"
    assert response["ETag"].startswith('"')
    assert response.content.count(b"BEGIN:VEVENT") == 10
    calendar_text = response.content.decode().replace("\r\n ", "")
    assert "SUMMARY:Wednesday\\, Nov 11 — Northeast Elementary — Grade 01" in calendar_text
    assert "✅ Cheese\\, Pizzable" in calendar_text
    assert "Served together: ❌ Fruit Cup" in calendar_text
    assert "[LIKED]" not in calendar_text and "[DISLIKED]" not in calendar_text
    event_dates = [
        line.split(":", 1)[1]
        for line in calendar_text.splitlines()
        if line.startswith("DTSTART;VALUE=DATE:")
    ]
    assert event_dates[0] == "20261111" and event_dates[-1] == "20261124"
    assert starts == [date(2026, 11, 9), date(2026, 11, 16), date(2026, 11, 23)]
    full_menu = (
        "https://menus.example.test/lunchbox/?week=2026-11-09&school=NORTHEAST_ELEMENTARY&grade=01"
    )
    assert calendar_text.count("URL:") == 10
    assert f"URL:{full_menu}" in calendar_text
    assert (
        "URL:https://menus.example.test/lunchbox/?week=2026-11-16&school=NORTHEAST_ELEMENTARY&grade=01"
        in calendar_text
    )
    assert (
        "URL:https://menus.example.test/lunchbox/?week=2026-11-23&school=NORTHEAST_ELEMENTARY&grade=01"
        in calendar_text
    )
    assert f"📋 FULL MENU\\n{full_menu}" in calendar_text
    uids = [line for line in calendar_text.splitlines() if line.startswith("UID:")]
    assert len(uids) == 10 and all(uid.endswith("@menus.example.test") for uid in uids)
    provider.assert_not_called()

    unchanged = client.get(url, HTTP_IF_NONE_MATCH=response["ETag"])
    assert unchanged.status_code == 304
    assert unchanged["ETag"] == response["ETag"]


def test_calendar_feed_rejects_invalid_or_non_default_tokens(client):
    assert client.get("/calendar/not-a-short-token.ics").status_code == 404

    token = calendar_feed.calendar_token()
    with override_settings(DEFAULT_GRADE="02"):
        assert calendar_feed.calendar_token() != token
        assert client.get(reverse("calendar_feed", kwargs={"token": token})).status_code == 404
