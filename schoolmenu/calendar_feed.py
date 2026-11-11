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

from .domain import default_monday, monday
from .provider import School
from .services import Selection

TOKEN_NAMESPACE = "schoolmenu.menu-calendar.v1"


def default_calendar_identity() -> Selection:
    """Return the deployment-configured school and grade as a validated selection."""
    return Selection.parse({})


def _scope_token(school: School, grade: str) -> str:
    message = f"{TOKEN_NAMESPACE}\0{school.name}\0{grade}".encode()
    digest = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def calendar_token(selection: Selection | None = None) -> str:
    """Return a compact, stable, opaque token for the selected school and grade."""
    identity = selection or default_calendar_identity()
    if identity.grade not in settings.SUPPORTED_GRADES:
        raise ValueError("Calendar grade is not supported")
    return _scope_token(identity.school, identity.grade)


def decode_calendar_token(token: str) -> Selection:
    """Validate a token against supported school/grade scopes and return its scope."""
    if not isinstance(token, str) or len(token) != 22:
        raise signing.BadSignature("Calendar token does not match a supported feed")
    identity = None
    for school in School:
        for grade in dict.fromkeys(settings.SUPPORTED_GRADES):
            if hmac.compare_digest(token, _scope_token(school, grade)):
                identity = Selection(school, grade, default_monday(timezone.localdate()))
    if identity is None:
        raise signing.BadSignature("Calendar token does not match a supported feed")
    return identity


def calendar_subscription_url(request, selection: Selection | None = None) -> str:
    """Create an absolute, stable URL for this school/grade calendar subscription."""
    path = reverse("calendar_feed", kwargs={"token": calendar_token(selection)})
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


def calendar_selections(identity: Selection, today: date | None = None) -> tuple[Selection, ...]:
    """Build weekly selections for one school/grade over the rolling calendar window."""
    return tuple(
        Selection(identity.school, identity.grade, start) for start in calendar_week_starts(today)
    )


def default_calendar_selections(today: date | None = None) -> tuple[Selection, ...]:
    """Build default-scope weekly selections for the rolling calendar window."""
    return calendar_selections(default_calendar_identity(), today)
