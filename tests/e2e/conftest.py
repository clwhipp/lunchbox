import json
import os
from datetime import date

import pytest

from schoolmenu import services
from tests.conftest import SAMPLES


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    return browser_type_launch_args | ({"executable_path": executable} if executable else {})


@pytest.fixture
def menu_server(monkeypatch, live_server):
    def fetch(selection, kind, serving_date):
        path = SAMPLES / f"{kind}-{serving_date.isoformat()}.json"
        return json.loads(path.read_text()) if path.exists() else {}

    monkeypatch.setattr(services, "fetch_provider", fetch)
    monkeypatch.setattr(services.timezone, "localdate", lambda: date(2026, 11, 11))
    return live_server.url


@pytest.fixture(autouse=True)
def images(context):
    context.route(
        "**/thumbnail/",
        lambda route: route.fulfill(
            status=200,
            content_type="image/svg+xml",
            body=(
                '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
                '<rect width="64" height="64" fill="#e0e9d4"/>'
                '<circle cx="32" cy="32" r="23" fill="#faf9f0"/></svg>'
            ),
        ),
    )
