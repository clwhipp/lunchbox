"""Opaque calendar capability tokens and rolling windows for menu feeds."""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import date, timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import timezone

from .domain import monday
from .services import Selection

TOKEN_NAMESPACE = "schoolmenu.menu-calendar.v1"


def default_calendar_identity() -> Selection:
    """Return the deployment-configured school and grade as a validated selection."""
    return Selection.parse({})


def calendar_token() -> str:
    """Return a compact, stable, opaque token for the configured calendar."""
    identity = default_calendar_identity()
    message = f"{TOKEN_NAMESPACE}\0{identity.school.name}\0{identity.grade}".encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def decode_calendar_token(token: str) -> Selection:
    """Validate an opaque token against the deployment's default feed identity."""
    expected = calendar_token()
    if len(token) != len(expected) or not hmac.compare_digest(token, expected):
        raise signing.BadSignature("Calendar token does not match the configured feed")
    return default_calendar_identity()


def calendar_subscription_url(request) -> str:
    """Create an absolute, stable URL suitable for an iCalendar subscription."""
    path = reverse("calendar_feed", kwargs={"token": calendar_token()})
    public_base = settings.CALENDAR_PUBLIC_BASE_URL
    if public_base:
        return urljoin(f"{public_base.rstrip('/')}/", path.lstrip("/"))
    return request.build_absolute_uri(path)


def calendar_week_starts(today: date | None = None) -> tuple[date, ...]:
    """Return every school week intersecting the next fourteen calendar days."""
    window_start = today or timezone.localdate()
    window_end = window_start + timedelta(days=13)
    week_start = monday(window_start)
    last_week_start = monday(window_end)
    starts = []
    while week_start <= last_week_start:
        if week_start + timedelta(days=4) >= window_start:
            starts.append(week_start)
        week_start += timedelta(days=7)
    return tuple(starts)


def default_calendar_selections(today: date | None = None) -> tuple[Selection, ...]:
    """Build weekly selections overlapping the deployment's rolling calendar window."""
    identity = default_calendar_identity()
    return tuple(
        Selection(identity.school, identity.grade, start) for start in calendar_week_starts(today)
    )
