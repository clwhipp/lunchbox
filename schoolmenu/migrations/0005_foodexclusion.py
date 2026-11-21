import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("schoolmenu", "0004_remove_sacklunch_grade")]

    operations = [
        migrations.CreateModel(
            name="FoodExclusion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now=True)),
                (
                    "food",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="schoolmenu.food",
                    ),
                ),
                (
                    "profile",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="schoolmenu.childprofile",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="foodexclusion",
            constraint=models.UniqueConstraint(
                fields=("profile", "food"), name="unique_food_exclusion"
            ),
        ),
    ]
