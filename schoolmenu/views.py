"""Thin HTTP views for a shared household menu."""

import hashlib
import time
from datetime import date
from urllib.parse import urlsplit

from django.conf import settings
from django.core import signing
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import Http404, HttpResponse, HttpResponseNotModified, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import calendar_feed, services
from .ics import build_calendar
from .images import thumbnail_bytes
from .models import Food


def selection_or_error(request, params):
    try:
        return services.Selection.parse(params)
    except ValueError as exc:
        return render(request, "menus/error.html", {"error": str(exc)}, status=400)


@require_http_methods(["GET", "POST"])
@never_cache
def index(request):
    reveal_calendar_url = request.method == "POST"
    params = request.POST if reveal_calendar_url else request.GET
    if reveal_calendar_url and params.get("calendar_action") != "reveal":
        return render(
            request,
            "menus/error.html",
            {"error": "Use the subscription button to reveal the calendar URL."},
            status=400,
        )
    selection = selection_or_error(request, params)
    if isinstance(selection, HttpResponse):
        return selection
    raw = params.get("week")
    if not reveal_calendar_url and (
        request.GET.get("date") or (raw and raw != selection.start.isoformat())
    ):
        return redirect(selection.url())
    context = services.load_week(selection)
    identity = selection
    context.update(
        calendar_subscription_url=(
            calendar_feed.calendar_subscription_url(request, selection)
            if reveal_calendar_url
            else None
        ),
        calendar_dialog_open=(reveal_calendar_url or request.GET.get("calendar_dialog") == "open"),
        calendar_school_label=identity.school.name.replace("_", " ").title(),
        calendar_grade=identity.grade,
    )
    return render(request, "menus/index.html", context)


@require_GET
def calendar_ics(request, token):
    try:
        identity = calendar_feed.decode_calendar_token(token)
    except signing.BadSignature as exc:
        raise Http404("Calendar subscription not found") from exc

    window_start = timezone.localdate()
    selections = calendar_feed.calendar_selections(identity, window_start)
    weeks = [services.load_week(selection) for selection in selections]
    school_label = identity.school.name.replace("_", " ").title()
    public_url = settings.CALENDAR_PUBLIC_BASE_URL or request.build_absolute_uri("/")
    uid_domain = urlsplit(public_url).hostname or "calendar.lunchbox"
    content = build_calendar(
        weeks,
        school_id=identity.school.value,
        school_key=identity.school.name,
        menu_base_url=public_url,
        school_label=school_label,
        grade=identity.grade,
        uid_domain=uid_domain,
        window_start=window_start,
        generated_at=timezone.now(),
    )
    etag = f'"{hashlib.sha256(content.encode("utf-8")).hexdigest()}"'
    response = (
        HttpResponseNotModified()
        if "*" in request.headers.get("If-None-Match", "").split(",")
        or etag in [tag.strip() for tag in request.headers.get("If-None-Match", "").split(",")]
        else HttpResponse(content, content_type="text/calendar; charset=utf-8")
    )
    response["Content-Disposition"] = 'inline; filename="lunchbox-menu.ics"'
    response["Cache-Control"] = "private, max-age=300"
    response["ETag"] = etag
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_POST
@never_cache
def sack_lunch(request):
    selection = selection_or_error(request, request.POST)
    if isinstance(selection, HttpResponse):
        return selection
    try:
        serving_date = date.fromisoformat(request.POST.get("serving_date", ""))
    except (TypeError, ValueError):
        return render(
            request,
            "menus/error.html",
            {"error": "Choose a valid serving date."},
            status=400,
        )
    confirmed_value = request.POST.get("confirmed", "")
    if confirmed_value not in {"true", "false", "1", "0", "on", "off"}:
        return render(
            request,
            "menus/error.html",
            {"error": "Choose whether this is a sack lunch."},
            status=400,
        )
    try:
        services.save_sack_lunch(selection, serving_date, confirmed_value in {"true", "1", "on"})
    except ValueError as exc:
        return render(request, "menus/error.html", {"error": str(exc)}, status=400)
    except DatabaseError:
        return render(
            request,
            "menus/error.html",
            {"error": "Could not save the sack lunch. Please retry."},
            status=503,
        )
    if request.headers.get("HX-Request") == "true":
        return render(request, "menus/week.html", services.load_week(selection, fetch=False))
    return redirect(selection.url())


@require_POST
@never_cache
def preference(request, food_id):
    selection = selection_or_error(request, request.POST)
    if isinstance(selection, HttpResponse):
        return selection
    food = get_object_or_404(Food, pk=food_id, school_id=selection.school.value)
    try:
        services.save_preference(food, request.POST.get("state", ""))
    except ValueError as exc:
        return render(request, "menus/error.html", {"error": str(exc)}, status=400)
    except DatabaseError:
        return render(
            request,
            "menus/error.html",
            {"error": "Could not save your preference. Please retry."},
            status=503,
        )
    if request.headers.get("HX-Request") == "true":
        return render(request, "menus/week.html", services.load_week(selection, fetch=False))
    return redirect(selection.url())


@require_GET
@never_cache
def detail(request, food_id):
    selection = selection_or_error(request, request.GET)
    if isinstance(selection, HttpResponse):
        return selection
    food = get_object_or_404(Food, pk=food_id, school_id=selection.school.value)
    try:
        serving_date = date.fromisoformat(request.GET.get("serving_date", ""))
    except ValueError as exc:
        raise Http404("Invalid serving date") from exc
    context = services.load_week(selection)
    matches = [
        item
        for day in context["days"]
        if day.date == serving_date
        for item in day.items
        if item.food_id == food.pk
    ]
    if not matches:
        raise Http404("This food is not listed for that serving date.")
    item = matches[0]
    context.update(item=item, ingredients=services.ingredients_for(selection, serving_date, item))
    template = (
        "menus/detail_content.html"
        if request.headers.get("HX-Request") == "true"
        else "menus/detail.html"
    )
    return render(request, template, context)


@require_GET
def thumbnail(request, food_id):
    food = get_object_or_404(Food, pk=food_id)
    image = thumbnail_bytes(food.pe_id, int(time.time() // 3600))
    if image is None:
        response = redirect(static("menus/plate.svg"))
        response["Cache-Control"] = "public, max-age=60"
        return response
    content, content_type = image
    response = HttpResponse(content, content_type=content_type)
    response["Cache-Control"] = "public, max-age=3600"
    return response


@require_GET
def live(request):
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request):
    try:
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if pending:
            return JsonResponse({"status": "migrations required"}, status=503)
        connection.ensure_connection()
    except DatabaseError:
        return JsonResponse({"status": "database unavailable"}, status=503)
    return JsonResponse({"status": "ready"})
