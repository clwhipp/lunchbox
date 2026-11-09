"""Persistent food identities, family preferences, and upstream cache."""

from django.db import models


class ChildProfile(models.Model):
    label = models.CharField(max_length=100, default="My child")


class Food(models.Model):
    school_id = models.UUIDField()
    source_id = models.PositiveIntegerField()
    pe_id = models.PositiveIntegerField()
    name = models.CharField(max_length=500)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school_id", "source_id"], name="unique_food")
        ]


class FoodPreference(models.Model):
    profile = models.ForeignKey(ChildProfile, on_delete=models.CASCADE)
    food = models.ForeignKey(Food, on_delete=models.CASCADE)
    value = models.CharField(max_length=8, choices=[("liked", "Liked"), ("disliked", "Disliked")])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["profile", "food"], name="unique_preference"),
            models.CheckConstraint(
                condition=models.Q(value__in=["liked", "disliked"]), name="valid_preference"
            ),
        ]


class MenuCache(models.Model):
    key = models.CharField(max_length=300, unique=True)
    payload = models.JSONField()
    fetched_at = models.DateTimeField()
    expires_at = models.DateTimeField()
