from datetime import date
from io import StringIO
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from schoolmenu import calendar_feed, services

pytestmark = pytest.mark.django_db


def test_once_refreshes_all_school_weeks_over_the_rolling_fourteen_day_window(monkeypatch):
    monkeypatch.setattr(calendar_feed.timezone, "localdate", lambda: date(2026, 11, 11))
    load_week = Mock(return_value={"menu_error": "", "stale": False, "days": []})
    monkeypatch.setattr(services, "load_week", load_week)
    output = StringIO()

    call_command("refresh_calendar_menus", "--once", stdout=output)

    assert [call.args[0].start for call in load_week.call_args_list] == [
        date(2026, 11, 9),
        date(2026, 11, 16),
        date(2026, 11, 23),
    ]
    assert all(call.kwargs == {} for call in load_week.call_args_list)
    assert "3 school weeks" in output.getvalue()


def test_periodic_worker_runs_immediately_and_recovers_from_a_failed_pass(monkeypatch):
    monkeypatch.setattr(calendar_feed.timezone, "localdate", lambda: date(2026, 11, 11))
    load_week = Mock(
        side_effect=[
            RuntimeError("temporary failure"),
            {"menu_error": "", "stale": False, "days": []},
            {"menu_error": "", "stale": False, "days": []},
            {"menu_error": "", "stale": False, "days": []},
            {"menu_error": "", "stale": False, "days": []},
            {"menu_error": "", "stale": False, "days": []},
        ]
    )
    monkeypatch.setattr(services, "load_week", load_week)
    sleep = Mock(side_effect=[None, KeyboardInterrupt])
    monkeypatch.setattr("schoolmenu.management.commands.refresh_calendar_menus.time.sleep", sleep)

    call_command("refresh_calendar_menus", stdout=StringIO())

    assert load_week.call_count == 6
    assert sleep.call_count == 2
    assert all(call.kwargs == {} for call in load_week.call_args_list)


def test_once_reports_failed_upstream_refresh(monkeypatch):
    monkeypatch.setattr(calendar_feed.timezone, "localdate", lambda: date(2026, 11, 11))
    load_week = Mock(return_value={"menu_error": "SchoolCafe unavailable", "stale": True})
    monkeypatch.setattr(services, "load_week", load_week)

    with pytest.raises(CommandError, match="Menu refresh failed"):
        call_command("refresh_calendar_menus", "--once", stdout=StringIO())

    assert load_week.call_count == 3
