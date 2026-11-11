import json
from copy import deepcopy
from datetime import date, timedelta

import pytest

from schoolmenu.domain import (
    Day,
    Group,
    Item,
    default_monday,
    link_served_together,
    monday,
    normalize_item,
    normalize_week,
    nutrients,
    provider_date,
    sack_lunch_days,
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
        ("2026-11-02", 46),
        ("2026-11-04", 27),
        ("2026-11-08", 27),
        ("2026-11-09", 36),
        ("2026-11-11", 17),
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
    assert sum(len(d.items) for d in days) == 36
    assert sum(bool(i.image) for d in days for i in d.items) == 36
    assert not any(i.category == "CONDIMENTS" for d in days for i in d.items)
    assert not days[2].items
    assert len(days[0].entrees) == 3
    assert days[0].entrees[0].name == "Cheese Pizzable"
    assert len(days[0].main_groups) == 4
    assert len(days[0].extra_groups) == 1
    assert days[0].entrees[0].nutrition[-1]["value"] == 674.63
    assert "May contain Soy" in days[0].entrees[0].allergens
    assert not any(d.incomplete for d in days)


def test_beef_taco_thumbnail_is_checked_even_when_flag_is_false(weekly):
    raw = next(
        item
        for day in weekly.values()
        for rows in day.values()
        for item in rows
        if item.get("MenuItemDescription") == "Beef Taco Meat"
    )
    assert raw["HasImage"] is False
    item = normalize_item(raw, "ENTREES")
    assert item is not None
    assert item.image == raw["ThumbnailImageURL"]


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
    assert all(not day.sack_lunch for day in days)


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
    "url,expected",
    [
        (None, ""),
        ("https://evil.com/a", ""),
        ("http://onlineservice.primeroedge.com/a", ""),
        (
            "https://onlineservice.primeroedge.com/a",
            "https://onlineservice.primeroedge.com/a",
        ),
    ],
)
def test_image_allowlist(url, expected):
    assert thumbnail(url) == expected


def item(state, category="ENTREES"):
    return Item(1, 2, "Food", category, "", "", "", [], preference=state)


def test_week_relationship_metadata_is_validated_and_linked(weekly):
    monday = weekly["11/9/2026"]
    entree_id = monday["ENTREES"][0]["PEMenuItemId"]
    choice_id = monday["VEGETABLES CHOICE BAR"][0]["PEMenuItemId"]
    weekly["_served_together"] = {
        "2026-11-09": [[entree_id, choice_id]],
        "bad date": [[entree_id, choice_id]],
        "11/10/2026": "not a list",
        "11/11/2026": [[True, choice_id], [entree_id, 0], [entree_id]],
        None: [[entree_id, choice_id]],
    }

    days = normalize_week(weekly, date(2026, 11, 9))

    assert days[0].entrees[0].related_items[0].pe_id == choice_id
    assert days[0].entrees[0].related_items[0].is_related_item
    assert not any(item.is_related_item for item in days[1].items)
    assert normalize_week({"_served_together": []}, date(2026, 11, 9))


def test_linked_choice_items_are_nested_under_the_parent_entree():
    parent = item("neutral")
    choice = Item(2, 3, "Nacho Cheese Doritos", "GRAINS", "1 pkg.", "", "", [])
    day = Day(
        date(2026, 11, 10), [Group("Entrées", "main", [parent]), Group("Grains", "extra", [choice])]
    )

    link_served_together([day], {day.date: [(parent.pe_id, choice.pe_id)]})

    assert parent.related_items == [choice]
    assert choice.is_related_item


def test_non_entree_or_missing_items_are_not_nested():
    entree = Item(1, 2, "Beef Taco Meat", "ENTREES", "", "", "", [])
    guacamole = Item(2, 3, "Guacamole", "VEGETABLES CHOICE BAR", "", "", "", [])
    salsa = Item(3, 4, "Salsa Cup", "VEGETABLES CHOICE BAR", "", "", "", [])
    day = Day(date(2026, 11, 10), [Group("Menu", "main", [entree, guacamole, salsa])])
    link_served_together(
        [day],
        {
            day.date: [
                (99, salsa.pe_id),
                (guacamole.pe_id, salsa.pe_id),
                (entree.pe_id, 99),
                (entree.pe_id, entree.pe_id),
            ]
        },
    )

    assert not entree.related_items
    assert not guacamole.related_items
    assert not salsa.is_related_item


def test_sack_lunch_confirmation_is_explicit_and_keeps_day_order():
    days = [Day(date(2026, 11, 9) + timedelta(days=offset)) for offset in range(5)]
    days[1].groups.append(Group("Entrées", "main", [item("disliked")]))
    days[2].incomplete = True

    confirmed = sack_lunch_days(days, {date(2026, 11, 11), date(2026, 11, 13)})

    assert confirmed == [days[2], days[4]]
    assert [day.sack_lunch for day in days] == [False, False, True, False, True]
