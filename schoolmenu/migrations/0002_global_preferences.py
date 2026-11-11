import django.db.models.deletion
from django.db import migrations, models


def move_preferences_to_global_food_ids(apps, schema_editor):
    Preference = apps.get_model("schoolmenu", "FoodPreference")
    alias = schema_editor.connection.alias
    rows = list(Preference.objects.using(alias).select_related("food").order_by("updated_at", "pk"))
    latest = {}
    for row in rows:
        row.pe_id = row.food.pe_id
        latest[(row.profile_id, row.pe_id)] = row
    Preference.objects.using(alias).bulk_update(rows, ["pe_id"])
    retained_ids = {row.pk for row in latest.values()}
    Preference.objects.using(alias).exclude(pk__in=retained_ids).delete()


def restore_food_links(apps, schema_editor):
    Food = apps.get_model("schoolmenu", "Food")
    Preference = apps.get_model("schoolmenu", "FoodPreference")
    alias = schema_editor.connection.alias
    for preference in Preference.objects.using(alias).filter(food_id__isnull=True).iterator():
        food_id = (
            Food.objects.using(alias)
            .filter(pe_id=preference.pe_id)
            .order_by("pk")
            .values_list("pk", flat=True)
            .first()
        )
        if food_id is None:
            raise RuntimeError(f"No Food row exists for PEMenuItemId {preference.pe_id}")
        Preference.objects.using(alias).filter(pk=preference.pk).update(food_id=food_id)


class Migration(migrations.Migration):
    dependencies = [("schoolmenu", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="foodpreference",
            name="pe_id",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.RunPython(
            move_preferences_to_global_food_ids,
            migrations.RunPython.noop,
        ),
        migrations.RemoveConstraint(
            model_name="foodpreference",
            name="unique_preference",
        ),
        migrations.AlterField(
            model_name="foodpreference",
            name="food",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="schoolmenu.food",
            ),
        ),
        migrations.RunPython(
            migrations.RunPython.noop,
            restore_food_links,
        ),
        migrations.AlterField(
            model_name="foodpreference",
            name="pe_id",
            field=models.PositiveIntegerField(),
        ),
        migrations.AddConstraint(
            model_name="foodpreference",
            constraint=models.UniqueConstraint(
                fields=("profile", "pe_id"),
                name="unique_preference",
            ),
        ),
    ]
