import sqlite3
from contextlib import closing
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Write a consistent online SQLite backup to a new file."

    def add_arguments(self, parser):
        parser.add_argument("destination")

    def handle(self, *args, **options):
        destination = Path(options["destination"]).resolve()
        # Exclusive creation prevents overwriting either live data or a backup.
        try:
            with destination.open("xb"):
                pass
        except OSError as exc:
            raise CommandError(f"Cannot create backup: {exc}") from exc
        connection.ensure_connection()
        with closing(sqlite3.connect(destination)) as target:
            connection.connection.backup(target)
        self.stdout.write(self.style.SUCCESS(f"Backup written to {destination}"))
