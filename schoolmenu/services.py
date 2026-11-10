"""Menu caching and persistence; preferences never require upstream access."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from threading import Lock
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .domain import default_monday, monday, normalize_week, provider_date, summarize
from .models import ChildProfile, Food, FoodPreference, MenuCache
from .provider import ProviderError, School, SchoolCafeClient

logger = logging.getLogger(__name__)
_refresh_locks = [Lock() for _ in range(32)]
_provider_lock = Lock()
_last_request = 0.0


@dataclass(frozen=True)
class Selection:
    school: School
    grade: str
    start: date

    @classmethod
    def parse(cls, params) -> Selection:
        try:
            school = School[params.get("school", settings.DEFAULT_SCHOOL)]
            grade = params.get("grade", settings.DEFAULT_GRADE)
            if grade not in settings.SUPPORTED_GRADES:
                raise ValueError("Choose a supported grade.")
            if params.get("week") and params.get("date"):
                raise ValueError("Choose one date selector.")
            raw_date = params.get("week") or params.get("date")
            start = (
                monday(date.fromisoformat(raw_date))
                if raw_date
                else default_monday(timezone.localdate())
            )
            # Navigation must remain representable at either end of this range.
            if not 2000 <= start.year <= 2099:
                raise ValueError("Choose a date between 2000 and 2099.")
            return cls(school, grade, start)
        except KeyError as exc:
            raise ValueError("Choose a supported school.") from exc

    def url(self, start: date | None = None) -> str:
        return "/?" + urlencode(
            {
                "week": (start or self.start).isoformat(),
                "school": self.school.name,
                "grade": self.grade,
            }
        )

    def cache_key(self, kind: str, serving_date: date) -> str:
        return f"v1:{self.school.value}:{self.grade}:Lunch:A Line:null:false:{kind}:{serving_date}"


def fetch_provider(selection: Selection, kind: str, serving_date: date) -> dict:
    """At most two attempts, serialized and paced across all request contexts."""
    global _last_request
    with _provider_lock:
        client = SchoolCafeClient(
            school=selection.school,
            grade=selection.grade,
            request_delay=0,
            timeout=settings.PROVIDER_TIMEOUT,
        )
        for attempt in range(2):
            time.sleep(max(0, 1 - (time.monotonic() - _last_request)))
            try:
                if kind == "weekly":
                    return client.get_weekly_menu(provider_date(serving_date))
                return client.get_daily_menu(provider_date(serving_date))
            except ProviderError as exc:
                if not exc.retryable or attempt:
                    raise
            finally:
                _last_request = time.monotonic()
    raise AssertionError("Unreachable provider state")  # pragma: no cover


@dataclass
class CachedMenu:
    payload: dict
    fetched_at: object = None
    stale: bool = False
    error: str = ""


def cached_menu(selection: Selection, kind: str, serving_date: date, *, fetch=True) -> CachedMenu:
    key = selection.cache_key(kind, serving_date)
    with _refresh_locks[hash(key) % len(_refresh_locks)]:
        now = timezone.now()
        cached = MenuCache.objects.filter(key=key).first()
        if cached and cached.expires_at > now:
            return CachedMenu(cached.payload, cached.fetched_at)
        error = "Saved menu is unavailable. Reload the page to refresh it."
        if fetch:
            try:
                payload = fetch_provider(selection, kind, serving_date)
                if not isinstance(payload, dict):
                    raise ProviderError("Invalid menu response")
                if kind == "weekly":
                    days = normalize_week(payload, serving_date)
                    published = any(day.items for day in days)
                else:
                    if not all(isinstance(rows, list) for rows in payload.values()):
                        raise ProviderError("Invalid daily response")
                    published = bool(payload)
                ttl = settings.MENU_TTL if published else settings.EMPTY_MENU_TTL
                MenuCache.objects.update_or_create(
                    key=key,
                    defaults={
                        "payload": payload,
                        "fetched_at": now,
                        "expires_at": now + timedelta(seconds=ttl),
                    },
                )
                return CachedMenu(payload, now)
            except ProviderError:
                logger.warning("SchoolCafe fetch failed for %s", key, exc_info=True)
                error = "SchoolCafe is unavailable. Please try again shortly."
        if cached and (now - cached.fetched_at).total_seconds() <= settings.STALE_MENU_TTL:
            return CachedMenu(cached.payload, cached.fetched_at, stale=True, error=error)
        return CachedMenu({}, error=error)


def default_profile() -> ChildProfile:
    return ChildProfile.objects.get_or_create(pk=1)[0]


def load_week(selection: Selection, *, fetch=True) -> dict:
    today = timezone.localdate()
    cached = cached_menu(selection, "weekly", selection.start, fetch=fetch)
    days = normalize_week(cached.payload, selection.start)
    items = [item for day in days for item in day.items]
    Food.objects.bulk_create(
        [
            Food(
                school_id=selection.school.value, source_id=i.source_id, pe_id=i.pe_id, name=i.name
            )
            for i in items
        ],
        ignore_conflicts=True,
    )
    foods = {
        f.source_id: f
        for f in Food.objects.filter(
            school_id=selection.school.value,
            source_id__in={i.source_id for i in items},
        )
    }
    preferences = dict(
        FoodPreference.objects.filter(
            profile=default_profile(),
            pe_id__in={i.pe_id for i in items},
        ).values_list("pe_id", "value")
    )
    for item in items:
        item.food_id = foods[item.source_id].pk
        item.preference = preferences.get(item.pe_id, "neutral")
    return {
        "days": days,
        "summary": summarize(days),
        "selection": selection,
        "fetched_at": cached.fetched_at,
        "stale": cached.stale,
        "menu_error": cached.error,
        "end": selection.start + timedelta(days=4),
        "previous_url": selection.url(selection.start - timedelta(days=7)),
        "next_url": selection.url(selection.start + timedelta(days=7)),
        "current_url": selection.url(default_monday(today)),
        "current_label": "Upcoming week" if today.weekday() >= 5 else "This week",
        "query": selection.url()[2:],
        "schools": [(s.name, s.name.replace("_", " ").title()) for s in School],
        "grades": settings.SUPPORTED_GRADES,
    }


def save_preference(food: Food, value: str) -> None:
    if value not in {"liked", "disliked", "neutral"}:
        raise ValueError("Choose liked, disliked, or neutral.")
    with transaction.atomic():
        profile = default_profile()
        if value == "neutral":
            FoodPreference.objects.filter(profile=profile, pe_id=food.pe_id).delete()
        else:
            FoodPreference.objects.update_or_create(
                profile=profile,
                pe_id=food.pe_id,
                defaults={"value": value, "food": food},
            )


def ingredients_for(selection: Selection, serving_date: date, item) -> str:
    cached = cached_menu(selection, "daily", serving_date)
    for rows in cached.payload.values():
        for raw in rows:
            if (
                isinstance(raw, dict)
                and raw.get("MenuItemId") == item.source_id
                and raw.get("PEMenuItemId") == item.pe_id
            ):
                # Never mix changed nutrient/allergen data with older ingredients.
                shared = {"Calories": item.nutrition[0]["value"], "AllergenDisplay": item.allergens}
                if any(
                    raw.get(key) != value
                    for key, value in shared.items()
                    if value is not None and key in raw and raw[key]
                ):
                    return (
                        "Ingredient details have changed. Refresh the weekly menu to review them."
                    )
                return str(
                    raw.get("SubIngredientsDisplay") or "Ingredient information not supplied."
                )
    return "Ingredient information is currently unavailable."
