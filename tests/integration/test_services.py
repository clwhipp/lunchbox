import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from threading import Event
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connections, transaction
from django.utils import timezone

from schoolmenu import services
from schoolmenu.models import ChildProfile, Food, FoodPreference, MenuCache
from schoolmenu.provider import ProviderError, School
from schoolmenu.services import Selection, cached_menu, ingredients_for, load_week, save_preference

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "params",
    [
        {"grade": "99"},
        {"school": "bad"},
        {"date": "bad"},
        {"week": "2026-11-09", "date": "2026-11-10"},
        {"week": "1990-01-01"},
        {"week": "2200-01-01"},
    ],
)
def test_invalid_selection(params):
    with pytest.raises(ValueError):
        Selection.parse(params)


@pytest.mark.parametrize(
    "now,expected",
    [
        (datetime(2026, 11, 9, 2, tzinfo=UTC), date(2026, 11, 9)),  # Sunday in Chicago.
        (datetime(2026, 11, 7, 2, tzinfo=UTC), date(2026, 11, 2)),  # Friday in Chicago.
    ],
)
def test_selection_uses_school_local_date(monkeypatch, now, expected):
    monkeypatch.setattr(services.timezone, "now", lambda: now)
    selected = Selection.parse({})
    assert selected.start == expected
    assert Selection.parse({"date": "2026-11-11"}).start == date(2026, 11, 9)
    assert selected.grade == "01"
    assert f"week={expected.isoformat()}" in selected.url()


def test_real_preferences_propagate_across_days_and_reloads(monkeypatch, weekly, selection):
    fetch = Mock(return_value=weekly)
    monkeypatch.setattr(services, "fetch_provider", fetch)
    week = load_week(selection)
    assert [len(week["summary"][s]) for s in ["pack", "school", "review", "unavailable"]] == [
        0,
        0,
        4,
        1,
    ]
    assert fetch.call_count == 1
    for item in week["days"][0].entrees:
        save_preference(Food.objects.get(pk=item.food_id), "disliked")
    chicken = Food.objects.get(source_id=43863)
    save_preference(chicken, "liked")
    save_preference(chicken, "liked")
    week = load_week(selection, fetch=False)
    assert [len(week["summary"][s]) for s in ["pack", "school", "review", "unavailable"]] == [
        1,
        2,
        1,
        1,
    ]
    assert [d.date.weekday() for d in week["summary"]["school"]] == [1, 3]
    assert FoodPreference.objects.count() == 4
    save_preference(chicken, "disliked")
    assert FoodPreference.objects.get(food=chicken).value == "disliked"
    save_preference(chicken, "neutral")
    assert not FoodPreference.objects.filter(food=chicken).exists()
    assert fetch.call_count == 1
    with pytest.raises(ValueError):
        save_preference(chicken, "both")


def test_context_and_profile_isolation(monkeypatch, weekly, selection):
    monkeypatch.setattr(services, "fetch_provider", Mock(return_value=weekly))
    week = load_week(selection)
    food = Food.objects.get(pk=week["days"][0].entrees[0].food_id)
    other = ChildProfile.objects.create(label="Other")
    FoodPreference.objects.create(profile=other, food=food, value="liked")
    assert load_week(selection)["days"][0].entrees[0].preference == "neutral"
    other_school = Selection(School.ABBIE_GROVE, "01", selection.start)
    assert load_week(other_school)["days"][0].entrees[0].food_id != food.pk
    assert MenuCache.objects.count() == 2


def test_database_constraints(monkeypatch, weekly, selection):
    monkeypatch.setattr(services, "fetch_provider", Mock(return_value=weekly))
    food = Food.objects.get(pk=load_week(selection)["days"][0].entrees[0].food_id)
    save_preference(food, "liked")
    profile = services.default_profile()
    for fields in [
        {"profile": profile, "food": food, "value": "disliked"},
        {"profile": profile, "food": food, "value": "invalid"},
    ]:
        with pytest.raises(IntegrityError), transaction.atomic():
            FoodPreference.objects.create(**fields)
    with pytest.raises(IntegrityError), transaction.atomic():
        Food.objects.create(
            school_id=food.school_id, source_id=food.source_id, pe_id=2, name="Duplicate"
        )


def test_expiry_stale_and_cutoff(monkeypatch, weekly, selection):
    fetch = Mock(return_value=weekly)
    monkeypatch.setattr(services, "fetch_provider", fetch)
    cached_menu(selection, "weekly", selection.start)
    entry = MenuCache.objects.get()
    assert (entry.expires_at - entry.fetched_at).total_seconds() == 900
    MenuCache.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    fetch.side_effect = ProviderError("down")
    stale = cached_menu(selection, "weekly", selection.start)
    assert stale.stale and stale.payload == weekly and stale.error
    assert MenuCache.objects.get().payload == weekly
    assert cached_menu(selection, "weekly", selection.start, fetch=False).stale
    MenuCache.objects.update(fetched_at=timezone.now() - timedelta(days=2))
    assert cached_menu(selection, "weekly", selection.start).payload == {}
    assert cached_menu(selection, "weekly", selection.start, fetch=False).fetched_at is None


@pytest.mark.parametrize(
    "payload,kind", [([], "weekly"), ({"11/9/2026": []}, "weekly"), ({"ENTREES": "bad"}, "daily")]
)
def test_invalid_response_not_cached(monkeypatch, payload, kind, selection):
    monkeypatch.setattr(services, "fetch_provider", Mock(return_value=payload))
    assert cached_menu(selection, kind, selection.start).error
    assert not MenuCache.objects.exists()


def test_empty_cache_has_shorter_ttl(monkeypatch, selection):
    monkeypatch.setattr(services, "fetch_provider", Mock(return_value={}))
    cached_menu(selection, "weekly", selection.start)
    entry = MenuCache.objects.get()
    assert (entry.expires_at - entry.fetched_at).total_seconds() == 300
    assert cached_menu(selection, "daily", selection.start, fetch=False).error


def test_daily_enrichment_preserves_weekly_nutrition(monkeypatch, weekly, daily, selection):
    fetch = Mock(side_effect=[weekly, daily])
    monkeypatch.setattr(services, "fetch_provider", fetch)
    item = load_week(selection)["days"][0].entrees[0]
    before = deepcopy(item.nutrition)
    assert "Cheese Blend" in ingredients_for(selection, selection.start, item)
    assert "Cheese Blend" in ingredients_for(selection, selection.start, item)
    assert item.nutrition == before and before[-1]["value"] == 674.63
    assert fetch.call_count == 2
    entry = MenuCache.objects.get(key=selection.cache_key("daily", selection.start))
    entry.payload["ENTREES"][0]["Calories"] = 999
    entry.save()
    assert "changed" in ingredients_for(selection, selection.start, item)
    entry.payload["ENTREES"][0]["Calories"] = 353
    entry.payload["ENTREES"][0]["SubIngredientsDisplay"] = ""
    entry.save()
    assert "not supplied" in ingredients_for(selection, selection.start, item)
    entry.payload = {"ENTREES": [None, {"MenuItemId": 999}]}
    entry.save()
    assert "unavailable" in ingredients_for(selection, selection.start, item)


def test_gateway_retry_policy(monkeypatch, selection):
    client = Mock()
    factory = Mock(return_value=client)
    monkeypatch.setattr(services, "SchoolCafeClient", factory)
    sleeps = []
    monkeypatch.setattr(services.time, "sleep", sleeps.append)
    monkeypatch.setattr(services.time, "monotonic", lambda: 10)
    monkeypatch.setattr(services, "_last_request", 10)
    client.get_weekly_menu.side_effect = [ProviderError("temporary", retryable=True), {"ok": 1}]
    assert services.fetch_provider(selection, "weekly", selection.start) == {"ok": 1}
    assert client.get_weekly_menu.call_count == 2 and sleeps == [1, 1]
    client.get_daily_menu.return_value = {"daily": 1}
    assert services.fetch_provider(selection, "daily", selection.start) == {"daily": 1}
    client.get_weekly_menu.side_effect = ProviderError("bad")
    with pytest.raises(ProviderError):
        services.fetch_provider(selection, "weekly", selection.start)
    client.get_weekly_menu.side_effect = ProviderError("persistent", retryable=True)
    with pytest.raises(ProviderError):
        services.fetch_provider(selection, "weekly", selection.start)


@pytest.mark.django_db(transaction=True)
def test_cold_requests_are_coalesced(monkeypatch, weekly, selection):
    started = Event()
    release = Event()

    def fetch(*args):
        started.set()
        assert release.wait(5)
        return weekly

    mock = Mock(side_effect=fetch)
    monkeypatch.setattr(services, "fetch_provider", mock)

    def load():
        try:
            return cached_menu(selection, "weekly", selection.start).payload
        finally:
            connections["default"].connection.close()
            connections.close_all()

    with ThreadPoolExecutor(2) as pool:
        one = pool.submit(load)
        assert started.wait(5)
        two = pool.submit(load)
        release.set()
        assert one.result() == two.result() == weekly
    assert mock.call_count == 1


@pytest.mark.django_db(transaction=True)
def test_backup_and_pruning_keep_preferences(monkeypatch, weekly, selection, tmp_path):
    monkeypatch.setattr(services, "fetch_provider", Mock(return_value=weekly))
    item = load_week(selection)["days"][0].entrees[0]
    save_preference(Food.objects.get(pk=item.food_id), "liked")
    backup = tmp_path / "backup.sqlite3"
    call_command("backup", str(backup))
    with closing(sqlite3.connect(backup)) as db:
        assert db.execute("SELECT value FROM schoolmenu_foodpreference").fetchall() == [("liked",)]
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with pytest.raises(CommandError):
        call_command("backup", str(backup))
    MenuCache.objects.update(fetched_at=timezone.now() - timedelta(days=91))
    call_command("prune_cache")
    assert not MenuCache.objects.exists() and FoodPreference.objects.count() == 1
