"""Thin HTTP views for a shared household menu."""

import time
from datetime import date

from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import services
from .images import thumbnail_bytes
from .models import Food


def selection_or_error(request, params):
    try:
        return services.Selection.parse(params)
    except ValueError as exc:
        return render(request, "menus/error.html", {"error": str(exc)}, status=400)


@require_GET
@never_cache
def index(request):
    selection = selection_or_error(request, request.GET)
    if isinstance(selection, HttpResponse):
        return selection
    raw = request.GET.get("week")
    if request.GET.get("date") or (raw and raw != selection.start.isoformat()):
        return redirect(selection.url())
    return render(request, "menus/index.html", services.load_week(selection))


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
