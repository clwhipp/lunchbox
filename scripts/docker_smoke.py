"""Exercise the production image using an isolated, disposable Compose volume.

Seeds captured public responses directly into the ordinary cache. No fixture
switch or test endpoint is added to the production application.
"""

import json
import os
import socket
import subprocess
import uuid
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]


class MenuHTML(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.forms = []
        self.states = {}
        self.current = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article" and "data-food-id" in attrs:
            self.states[attrs["data-food-id"]] = attrs["data-preference"]
        if tag == "form" and attrs.get("class") == "preference-form":
            self.current = {"action": attrs["action"], "data": {}}
            self.forms.append(self.current)
        if tag == "input" and self.current is not None and attrs.get("name"):
            self.current["data"][attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


def main():
    project = "schoolcafe-smoke-" + uuid.uuid4().hex[:10]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ | {
        "APP_PORT": str(port),
        "BIND_ADDRESS": "127.0.0.1",
        "LUNCHBOX_IMAGE": "lunchbox:local",
    }

    def compose(*args, input=None, check=True):
        result = subprocess.run(
            ["docker", "compose", "--project-name", project, *args],
            cwd=ROOT,
            env=env,
            input=input,
            text=True,
            capture_output=True,
            timeout=120,
        )
        if check and result.returncode:
            raise RuntimeError(
                f"Compose {' '.join(args[:3])} failed:\n{result.stderr}\n{result.stdout}"
            )
        return result

    def progress(message):
        print(message, flush=True)

    try:
        failed = compose(
            "run",
            "--rm",
            "-T",
            "web",
            "gunicorn",
            "schoolmenu.config.wsgi:application",
            check=False,
        )
        assert failed.returncode != 0, "An unmigrated container must not start"
        compose("run", "--rm", "-T", "web", "python", "manage.py", "migrate", "--noinput")
        progress("PASS: empty-volume permissions and migrations; unmigrated startup rejected")
        seed = """
import os, sys, json, django
from datetime import date, timedelta
os.environ.setdefault('DJANGO_SETTINGS_MODULE','schoolmenu.config.settings')
django.setup()
from django.utils import timezone
from schoolmenu.services import Selection
from schoolmenu.provider import School
from schoolmenu.models import MenuCache
s=Selection(School.NORTHEAST_ELEMENTARY,'01',date(2026,11,9))
now=timezone.now()
for kind,payload in json.load(sys.stdin).items():
    MenuCache.objects.create(key=s.cache_key(kind,s.start),payload=payload,
        fetched_at=now,expires_at=now+timedelta(hours=1))
"""
        samples = ROOT / "docs/api_samples"
        payload = {
            kind: json.loads((samples / f"{kind}-2026-11-09.json").read_text())
            for kind in ("weekly", "daily")
        }
        compose("run", "--rm", "-T", "web", "python", "-c", seed, input=json.dumps(payload))
        compose("up", "-d", "--wait", "--wait-timeout", "45")
        assert compose("exec", "-T", "web", "id", "-u").stdout.strip() == "10001"
        base = f"http://127.0.0.1:{port}"
        opener = build_opener(HTTPCookieProcessor(CookieJar()))
        query = urlencode({"week": "2026-11-09", "school": "NORTHEAST_ELEMENTARY", "grade": "01"})

        def menu():
            return MenuHTML(opener.open(base + "/?" + query, timeout=10).read().decode())

        first, second = menu().forms[:2]
        expected = {}
        for form, value in ((first, "liked"), (second, "disliked")):
            request = Request(
                base + form["action"], data=urlencode(form["data"] | {"state": value}).encode()
            )
            opener.open(request, timeout=10).read()
            expected[form["action"].split("/")[2]] = value

        def verify():
            states = menu().states
            assert all(states.get(key) == value for key, value in expected.items())

        verify()
        detail_url = (
            base
            + first["action"].replace("preference/", "")
            + "?"
            + query
            + "&serving_date=2026-11-09"
        )
        assert "674.63" in opener.open(detail_url, timeout=10).read().decode()
        progress(
            "PASS: healthy non-root server, CSRF-protected writes, "
            "green/red states, and nutrient details"
        )
        compose("restart", "web")
        compose("up", "-d", "--wait", "--wait-timeout", "45")
        verify()
        compose("up", "-d", "--force-recreate", "--wait", "--wait-timeout", "45")
        verify()
        progress("PASS: saved preferences survive restart and container recreation")
        compose(
            "exec", "-T", "web", "python", "manage.py", "backup", "/data/verified-backup.sqlite3"
        )
        restore = """
import shutil, sqlite3
from contextlib import closing
shutil.copyfile('/data/verified-backup.sqlite3','/data/restored.sqlite3')
with closing(sqlite3.connect('/data/restored.sqlite3')) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    values=sorted(row[0] for row in db.execute('SELECT value FROM schoolmenu_foodpreference'))
    assert values==['disliked','liked']
"""
        compose("exec", "-T", "web", "python", "-c", restore)
        progress("PASS: online backup restores a consistent SQLite database with both preferences")
    finally:
        compose("down", "--volumes", "--remove-orphans", check=False)


if __name__ == "__main__":
    main()
