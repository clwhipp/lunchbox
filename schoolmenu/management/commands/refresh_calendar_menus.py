"""Refresh menus for the next fourteen days on a repeating schedule."""

from __future__ import annotations

import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from schoolmenu import calendar_feed, services

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Refresh the configured school and grade menus covering the next fourteen days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Refresh all overlapping school weeks once, then exit.",
        )

    def handle(self, *args, **options):
        if options["once"]:
            self.refresh_once()
            return

        self.stdout.write(
            "Refreshing the default calendar every "
            f"{settings.CALENDAR_REFRESH_INTERVAL_SECONDS} seconds."
        )
        while True:
            try:
                self.refresh_once()
            except Exception:
                logger.exception(
                    "Calendar menu refresh failed; the previous cache remains available."
                )
            try:
                time.sleep(settings.CALENDAR_REFRESH_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                return

    def refresh_once(self):
        failures = []
        selections = calendar_feed.default_calendar_selections()
        for selection in selections:
            try:
                result = services.load_week(selection)
                if result.get("menu_error"):
                    logger.warning(
                        "Calendar menu refresh failed for %s grade %s week %s: %s",
                        selection.school.name,
                        selection.grade,
                        selection.start,
                        result["menu_error"],
                    )
                    failures.append(selection.start.isoformat())
                    continue
            except Exception:
                logger.exception(
                    "Calendar menu refresh failed for %s grade %s week %s.",
                    selection.school.name,
                    selection.grade,
                    selection.start,
                )
                failures.append(selection.start.isoformat())
                continue
            self.stdout.write(
                f"Refreshed {selection.school.name} grade {selection.grade} week {selection.start}."
            )
        if failures:
            raise CommandError("Menu refresh failed for week(s): " + ", ".join(failures))
        self.stdout.write(
            self.style.SUCCESS(f"Menu cache refreshed for {len(selections)} school weeks.")
        )
