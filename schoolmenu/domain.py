"""Pure menu normalization, calendar arithmetic, and lunch decisions."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from .provider import ProviderError

CATEGORIES = {
    "ENTREES": ("Entrées", "main"),
    "VEGETABLE SERVED": ("Vegetables · served", "main"),
    "VEGETABLES CHOICE BAR": ("Vegetables · choice bar", "main"),
    "MILK": ("Drinks", "main"),
    "DRINKS": ("Drinks", "main"),
    "FRUITS": ("Fruit", "extra"),
    "GRAINS": ("Grains", "extra"),
}
HIDDEN_CATEGORIES = {"CONDIMENTS"}
NUTRIENTS = (
    ("Calories", "Calories", "kcal"),
    ("TotalFat", "Total fat", "g"),
    ("SatFat", "Saturated fat", "g"),
    ("Carbs", "Carbohydrates", "g"),
    ("Sodium", "Sodium", "mg"),
)


def monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def default_monday(today: date) -> date:
    """Weekdays show this school week; weekends show the upcoming school week."""
    start = monday(today)
    return start + timedelta(days=7) if today.weekday() >= 5 else start


def provider_date(value: date) -> str:
    return f"{value.month}/{value.day}/{value.year}"


def positive_id(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def thumbnail(url: object) -> str:
    if not isinstance(url, str):
        return ""
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc == "onlineservice.primeroedge.com":
        return url
    return ""


def nutrients(raw: dict) -> list[dict]:
    result = []
    for key, label, unit in NUTRIENTS:
        value = raw.get(key)
        valid = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value >= 0
        )
        result.append({"label": label, "value": value if valid else None, "unit": unit})
    return result


@dataclass
class Item:
    source_id: int
    pe_id: int
    name: str
    category: str
    serving_size: str
    image: str
    allergens: str
    nutrition: list[dict]
    food_id: int = 0
    preference: str = "neutral"
    related_items: list[Item] = field(default_factory=list)
    is_related_item: bool = False


@dataclass
class Group:
    label: str
    section: str
    items: list[Item] = field(default_factory=list)


@dataclass
class Day:
    date: date
    groups: list[Group] = field(default_factory=list)
    incomplete: bool = False
    sack_lunch: bool = False

    @property
    def items(self) -> list[Item]:
        return [item for group in self.groups for item in group.items]

    @property
    def entrees(self) -> list[Item]:
        return [item for item in self.items if item.category == "ENTREES"]

    @property
    def main_groups(self) -> list[Group]:
        return [g for g in self.groups if g.section == "main"]

    @property
    def extra_groups(self) -> list[Group]:
        return [g for g in self.groups if g.section == "extra"]


def normalize_item(raw: object, category: str) -> Item | None:
    if not isinstance(raw, dict):
        raise ValueError("Invalid menu item")
    if raw.get("MenuItemId") == 0 and raw.get("PEMenuItemId") == 0:
        return None
    if not positive_id(raw.get("MenuItemId")) or not positive_id(raw.get("PEMenuItemId")):
        raise ValueError("Invalid menu identity")
    name = raw.get("MenuItemDescription")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Missing food description")
    return Item(
        source_id=raw["MenuItemId"],
        pe_id=raw["PEMenuItemId"],
        name=name.strip(),
        category=category,
        serving_size=str(raw.get("ServingSizeByGrade") or ""),
        image=thumbnail(raw.get("ThumbnailImageURL")),
        allergens=str(raw.get("AllergenDisplay") or "Allergen information not supplied."),
        nutrition=nutrients(raw),
    )


def normalize_week(payload: object, start: date) -> list[Day]:
    if not isinstance(payload, dict):
        raise ProviderError("Invalid weekly response")
    days = []
    for offset in range(5):
        serving_date = start + timedelta(days=offset)
        day = Day(serving_date)
        categories = payload.get(provider_date(serving_date), {})
        if not isinstance(categories, dict):
            raise ProviderError("Invalid day response")
        for category, rows in categories.items():
            if category in HIDDEN_CATEGORIES:
                continue
            label, section = CATEGORIES.get(category, (f"Other · {category}", "extra"))
            group = Group(label, section)
            if not isinstance(rows, list):
                day.incomplete = True
                continue
            for raw in rows:
                try:
                    item = normalize_item(raw, category)
                except ValueError:
                    day.incomplete = True
                    continue
                if item is not None:
                    group.items.append(item)
            if group.items:
                day.groups.append(group)
        # Provider dictionary/list order is stable; DisplayOrder often ties.
        days.append(day)
    raw_relationships = payload.get("_served_together", {})
    relationships: dict[date, list[tuple[int, int]]] = {}
    if isinstance(raw_relationships, dict):
        for day_key, pairs in raw_relationships.items():
            try:
                serving_day = (
                    date.fromisoformat(day_key)
                    if "-" in day_key
                    else datetime.strptime(day_key, "%m/%d/%Y").date()
                )
            except (TypeError, ValueError):
                continue
            if not isinstance(pairs, list):
                continue
            valid_pairs = []
            for pair in pairs:
                if (
                    isinstance(pair, list)
                    and len(pair) == 2
                    and positive_id(pair[0])
                    and positive_id(pair[1])
                ):
                    valid_pairs.append((pair[0], pair[1]))
            relationships[serving_day] = valid_pairs
    link_served_together(days, relationships)
    return days


def link_served_together(days: list[Day], relationships: dict[date, list[tuple[int, int]]]) -> None:
    """Nest provider-reported choice items under their parent entrée."""
    for day in days:
        items_by_id = {item.pe_id: item for item in day.items}
        for parent_id, child_id in relationships.get(day.date, []):
            parent = items_by_id.get(parent_id)
            child = items_by_id.get(child_id)
            if parent is None or child is None or parent.category != "ENTREES" or parent is child:
                continue
            if child not in parent.related_items:
                parent.related_items.append(child)
            child.is_related_item = True


def sack_lunch_days(days: list[Day], confirmed_dates: set[date]) -> list[Day]:
    """Mark and return only the days explicitly confirmed for a sack lunch."""
    confirmed = []
    for day in days:
        day.sack_lunch = day.date in confirmed_dates
        if day.sack_lunch:
            confirmed.append(day)
    return confirmed
