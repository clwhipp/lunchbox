import json
from copy import deepcopy
from datetime import date, timedelta

import pytest

from schoolmenu.domain import (
    Day,
    Group,
    Item,
    default_monday,
    monday,
    normalize_item,
    normalize_week,
    nutrients,
    provider_date,
    summarize,
    thumbnail,
)
from schoolmenu.provider import ProviderError
from tests.conftest import SAMPLES


@pytest.mark.parametrize(
    "today,expected",
    [
        (date(2026, 11, 6), date(2026, 11, 2)),
        (date(2026, 11, 7), date(2026, 11, 9)),
        (date(2026, 11, 8), date(2026, 11, 9)),
        (date(2026, 11, 9), date(2026, 11, 9)),
        (date(2026, 11, 11), date(2026, 11, 9)),
        (date(2023, 12, 31), date(2024, 1, 1)),
        (date(2026, 3, 8), date(2026, 3, 9)),
        (date(2026, 11, 1), date(2026, 11, 2)),
    ],
)
def test_weekend_defaults_advance_to_next_school_week(today, expected):
    assert default_monday(today) == expected


@pytest.mark.parametrize(
    "day,count",
    [
        ("2026-11-02", 55),
        ("2026-11-04", 32),
        ("2026-11-08", 36),
        ("2026-11-09", 47),
        ("2026-11-11", 21),
        ("2026-12-28", 0),
    ],
)
def test_all_captured_weekly_contracts(day, count):
    payload = json.loads((SAMPLES / f"weekly-{day}.json").read_text())
    days = normalize_week(payload, date.fromisoformat(day))
    assert len(days) == 5
    assert sum(len(d.items) for d in days) == count
    assert not any(d.incomplete for d in days)


@pytest.mark.parametrize(
    "start", [date(2026, 11, 2), date(2026, 12, 28), date(2024, 2, 26), date(2026, 3, 2)]
)
def test_calendar_always_uses_monday(start):
    for offset in range(7):
        assert monday(start + timedelta(days=offset)) == start
    assert monday(start + timedelta(days=7)) == start + timedelta(days=7)
    assert provider_date(start) == f"{start.month}/{start.day}/{start.year}"


def test_real_week(weekly):
    days = normalize_week(weekly, date(2026, 11, 9))
    assert len(days) == 5
    assert sum(len(d.items) for d in days) == 47
    assert sum(bool(i.image) for d in days for i in d.items) == 23
    assert not days[2].items
    assert len(days[0].entrees) == 3
    assert days[0].entrees[0].name == "Cheese Pizzable"
    assert len(days[0].main_groups) == 4
    assert len(days[0].extra_groups) == 2
    assert days[0].entrees[0].nutrition[-1]["value"] == 674.63
    assert "May contain Soy" in days[0].entrees[0].allergens
    assert not any(d.incomplete for d in days)


def test_unknown_malformed_and_missing(weekly):
    data = deepcopy(weekly)
    data["11/9/2026"]["NEW CATEGORY"] = [data["11/9/2026"]["ENTREES"][0]]
    data["11/10/2026"]["ENTREES"] = "invalid"
    data["11/12/2026"]["ENTREES"].append(None)
    del data["11/13/2026"]
    days = normalize_week(data, date(2026, 11, 9))
    assert days[0].extra_groups[-1].label == "Other · NEW CATEGORY"
    assert days[1].incomplete and days[3].incomplete
    assert not days[4].items
    assert len(summarize(days)["review"]) == 3
    assert days[1].status_label == "Needs review"


@pytest.mark.parametrize("payload", [[], None, {"11/9/2026": []}])
def test_invalid_root_or_day(payload):
    with pytest.raises(ProviderError):
        normalize_week(payload, date(2026, 11, 9))


@pytest.mark.parametrize(
    "change",
    [
        {"MenuItemId": None},
        {"MenuItemId": True},
        {"PEMenuItemId": 0},
        {"MenuItemDescription": " "},
        {"MenuItemDescription": None},
    ],
)
def test_invalid_items(change, weekly):
    item = weekly["11/9/2026"]["ENTREES"][0] | change
    with pytest.raises(ValueError):
        normalize_item(item, "ENTREES")


def test_placeholder_and_missing_optional_values():
    assert normalize_item({"MenuItemId": 0, "PEMenuItemId": 0}, "ENTREES") is None
    item = normalize_item(
        {"MenuItemId": 1, "PEMenuItemId": 2, "MenuItemDescription": " Name "}, "ENTREES"
    )
    assert item.name == "Name" and item.serving_size == "" and not item.image
    assert item.allergens == "Allergen information not supplied."


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, 0),
        (1.2, 1.2),
        (None, None),
        (True, None),
        (-1, None),
        (float("inf"), None),
        ("10", None),
    ],
)
def test_nutrients_missing_is_not_zero(value, expected):
    assert nutrients({"Calories": value})[0]["value"] == expected


@pytest.mark.parametrize(
    "url,flag,expected",
    [
        (None, True, ""),
        ("https://evil.com/a", True, ""),
        ("http://onlineservice.primeroedge.com/a", True, ""),
        ("https://onlineservice.primeroedge.com/a", False, ""),
        (
            "https://onlineservice.primeroedge.com/a",
            True,
            "https://onlineservice.primeroedge.com/a",
        ),
    ],
)
def test_image_allowlist(url, flag, expected):
    assert thumbnail(url, flag) == expected


def item(state, category="ENTREES"):
    return Item(1, 2, "Food", category, "", "", "", [], preference=state)


@pytest.mark.parametrize(
    "states,expected",
    [
        ([], "unavailable"),
        (["neutral"], "review"),
        (["disliked", "neutral"], "review"),
        (["disliked", "disliked"], "pack"),
        (["liked", "disliked"], "school"),
        (["neutral", "liked"], "school"),
    ],
)
def test_lunch_decision_table(states, expected):
    day = Day(date(2026, 11, 9), [Group("Entrées", "main", [item(s) for s in states])])
    summary = summarize([day])
    assert summary[expected] == [day]
    assert sum(map(len, summary.values())) == 1


def test_side_preferences_and_incomplete_entrees():
    day = Day(date(2026, 11, 9), [Group("Vegetables", "main", [item("liked", "VEGETABLE SERVED")])])
    assert summarize([day])["unavailable"] == [day]
    day.groups.append(Group("Entrées", "main", [item("disliked")]))
    day.incomplete = True
    assert summarize([day])["review"] == [day]
