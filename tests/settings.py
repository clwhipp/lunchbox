import os

os.environ.setdefault("DJANGO_SECRET_KEY", "isolated-test-key-never-used-in-deployment")
# Playwright's synchronous test API keeps an event loop on the test thread.
# ORM setup/teardown there is serial; application ORM work runs on WSGI threads.
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

from schoolmenu.config.settings import *  # noqa: E402,F403

STORAGES = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
