import uuid
from datetime import date, timedelta

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


@pytest.mark.django_db(transaction=True)
def test_migration_merges_duplicate_confirmations_across_grades():
    before = [("schoolmenu", "0003_sacklunch")]
    MigrationExecutor(connection).migrate(before)
    old_apps = MigrationExecutor(connection).loader.project_state(before).apps
    ChildProfile = old_apps.get_model("schoolmenu", "ChildProfile")
    SackLunch = old_apps.get_model("schoolmenu", "SackLunch")
    profile = ChildProfile.objects.create()
    fields = {
        "profile_id": profile.pk,
        "school_id": uuid.UUID("3b1df853-0744-4fae-9de7-02ecd78c6e4a"),
        "week_start": date(2026, 11, 9),
        "serving_date": date(2026, 11, 9),
    }
    previous = SackLunch.objects.create(grade="01", **fields)
    latest = SackLunch.objects.create(grade="02", **fields)
    SackLunch.objects.filter(pk=previous.pk).update(updated_at=timezone.now() - timedelta(days=1))

    after = [("schoolmenu", "0004_remove_sacklunch_grade")]
    MigrationExecutor(connection).migrate(after)
    current_apps = MigrationExecutor(connection).loader.project_state(after).apps
    CurrentSackLunch = current_apps.get_model("schoolmenu", "SackLunch")

    rows = list(CurrentSackLunch.objects.all())
    assert len(rows) == 1
    assert rows[0].pk == latest.pk
    assert rows[0].serving_date == date(2026, 11, 9)

    MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
