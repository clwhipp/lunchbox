"""Dependency-free RFC 5545 output for the menu subscription feed."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode, urljoin

from django.utils import timezone

from .domain import monday


def escape_ical_text(value: str) -> str:
    """Escape RFC 5545 TEXT values, including embedded line breaks."""
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def fold_ical_line(line: str) -> str:
    """Fold a content line at 75 UTF-8 octets without splitting a codepoint."""
    physical_lines: list[str] = []
    current = ""
    current_size = 0
    limit = 75
    for character in line:
        char_size = len(character.encode("utf-8"))
        if current_size + char_size > limit:
            physical_lines.append(current)
            current = " "
            current_size = 1
        current += character
        current_size += char_size
    physical_lines.append(current)
    return "\r\n".join(physical_lines)


def _content_line(name: str, value: str) -> str:
    return fold_ical_line(f"{name}:{escape_ical_text(value)}")


def _uri_line(name: str, value: str) -> str:
    """Fold a URI property without applying TEXT escaping to the URI."""
    return fold_ical_line(f"{name}:{value}")


def _full_menu_url(menu_base_url: str, school_key: str, grade: str, serving_date: date) -> str:
    query = urlencode(
        {
            "week": monday(serving_date).isoformat(),
            "school": school_key,
            "grade": grade,
        }
    )
    return urljoin(f"{menu_base_url.rstrip('/')}/", f"?{query}")


def _utc_timestamp(value: datetime) -> str:
    if timezone.is_naive(value):
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _preference_label(item: Any) -> str:
    markers = {"liked": "✅ ", "disliked": "❌ "}
    return markers.get(item.preference, "") + item.name


def _description_section(item: Any) -> str:
    if item.category == "ENTREES":
        return "main"
    if item.category in {"MILK", "DRINKS"}:
        return "drinks"
    return "sides"


def _day_description(day: Any, stale: bool, menu_url: str) -> str:
    lines = []
    if stale:
        lines.append("WARNING: Menu data may be out of date.")
    if day.incomplete:
        lines.append("WARNING: Some menu information is incomplete.")
    section_items: dict[str, list[str]] = {"main": [], "sides": [], "drinks": []}
    seen: set[int] = set()
    for group in day.groups:
        for item in group.items:
            if item.is_related_item or item.pe_id in seen:
                continue
            seen.add(item.pe_id)
            section = section_items[_description_section(item)]
            section.append(f"• {_preference_label(item)}")
            for related in item.related_items:
                if related.pe_id in seen:
                    continue
                seen.add(related.pe_id)
                section.append(f"  ↳ Served together: {_preference_label(related)}")
    titles = {
        "main": "MAIN ENTRÉES",
        "sides": "🥦 SIDES",
        "drinks": "🥛 MILK & DRINKS",
    }
    for name, title in titles.items():
        if section_items[name]:
            if lines:
                lines.append("")
            lines.append(title)
            lines.extend(section_items[name])
    if not seen:
        if lines:
            lines.append("")
        lines.append("No menu published yet.")
    if lines:
        lines.append("")
    lines.extend(["📋 FULL MENU", menu_url])
    return "\n".join(lines)


def _event_uid(school_id: str, grade: str, serving_date: date, domain: str) -> str:
    return f"lunchbox-{school_id}-grade-{grade}-{serving_date:%Y%m%d}@{domain}"


def build_calendar(
    weeks: list[dict[str, Any]],
    *,
    school_id: str,
    school_key: str,
    menu_base_url: str,
    school_label: str,
    grade: str,
    uid_domain: str = "calendar.lunchbox",
    window_start: date | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Render weekly contexts as all-day weekday events in an iCalendar feed."""
    generated_at = generated_at or timezone.now()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Lunchbox//School Menu Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    lines.append(_content_line("X-WR-CALNAME", f"Lunchbox — {school_label} — Grade {grade}"))
    lines.append(
        _content_line(
            "X-WR-CALDESC",
            f"Two-week school menu for {school_label}, Grade {grade}. "
            "Preference markers reflect the household's saved likes and dislikes.",
        )
    )
    window_end = window_start + timedelta(days=14) if window_start is not None else None
    for week in weeks:
        timestamp = week.get("fetched_at") or generated_at
        stale = bool(week.get("stale"))
        for day in week["days"]:
            if window_start is not None and window_end is not None:
                if not (window_start <= day.date < window_end and day.date.weekday() < 5):
                    continue
            next_day = day.date + timedelta(days=1)
            summary = (
                f"{day.date:%A}, {day.date:%b} {day.date.day} — {school_label} — Grade {grade}"
            )
            menu_url = _full_menu_url(menu_base_url, school_key, grade, day.date)
            description = _day_description(day, stale, menu_url)
            event_lines = [
                "BEGIN:VEVENT",
                _content_line("UID", _event_uid(school_id, grade, day.date, uid_domain)),
                f"DTSTAMP:{_utc_timestamp(timestamp)}",
                f"DTSTART;VALUE=DATE:{day.date:%Y%m%d}",
                f"DTEND;VALUE=DATE:{next_day:%Y%m%d}",
                _content_line("SUMMARY", summary),
                _uri_line("URL", menu_url),
                _content_line("DESCRIPTION", description),
                "END:VEVENT",
            ]
            lines.extend(event_lines)
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
