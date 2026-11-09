"""Pure menu normalization, calendar arithmetic, and lunch decisions."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
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
    "CONDIMENTS": ("Condiments", "extra"),
}
NUTRIENTS = (
    ("Calories", "Calories", "kcal"),
    ("TotalFat", "Total fat", "g"),
    ("SatFat", "Saturated fat", "g"),
    ("Carbs", "Carbohydrates", "g"),
    ("Sodium", "Sodium", "mg"),
)
STATUSES = {
    "pack": "Lunch from home likely",
    "school": "School lunch likely",
    "review": "Needs review",
    "unavailable": "No entrée menu published",
}


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


def thumbnail(url: object, has_image: object) -> str:
    if not has_image or not isinstance(url, str):
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
    status: str = "unavailable"

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

    @property
    def status_label(self) -> str:
        return STATUSES[self.status]


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
        image=thumbnail(raw.get("ThumbnailImageURL"), raw.get("HasImage")),
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
    return days


def summarize(days: list[Day]) -> dict[str, list[Day]]:
    summary: dict[str, list[Day]] = {status: [] for status in STATUSES}
    for day in days:
        entrees = day.entrees
        if day.incomplete:
            status = "review"
        elif not entrees:
            status = "unavailable"
        elif any(item.preference == "liked" for item in entrees):
            status = "school"
        elif all(item.preference == "disliked" for item in entrees):
            status = "pack"
        else:
            status = "review"
        day.status = status
        summary[status].append(day)
    return summary
