from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from schoolmenu.models import MenuCache


class Command(BaseCommand):
    help = "Remove upstream cache entries fetched more than 90 days ago."

    def handle(self, *args, **options):
        count, _ = MenuCache.objects.filter(
            fetched_at__lt=timezone.now() - timedelta(days=90)
        ).delete()
        self.stdout.write(f"Removed {count} cache entries.")
