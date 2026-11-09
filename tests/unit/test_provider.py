import json
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from schoolmenu.provider import ProviderError, School, SchoolCafeClient


@pytest.mark.parametrize(
    "args,error",
    [
        ({"request_delay": -1}, ValueError),
        ({"timeout": 0}, ValueError),
        ({"school": "bad"}, TypeError),
    ],
)
def test_client_validation(args, error):
    with pytest.raises(error):
        SchoolCafeClient(**args)


def test_url_and_configuration():
    client = SchoolCafeClient()
    client.configure(
        school=School.ABBIE_GROVE, grade="01", person_id=None, enabled_weekend_menus=False
    )
    query = parse_qs(urlparse(client.build_weekly_url("11/9/2026")).query)
    assert query["SchoolId"] == [School.ABBIE_GROVE.value]
    assert query["PersonId"] == ["null"] and query["Grade"] == ["01"]
    assert query["enabledWeekendMenus"] == ["false"]
    assert "enabledWeekendMenus" not in client.build_daily_url()
    assert client.serving_date in client.build_url("Daily").replace("%2F", "/")
    assert client._as_text(True) == "true" and client._as_text(4) == "4"
    client.configure(enabled_weekend_menus=True)
    assert "enabledWeekendMenus=true" in client.build_weekly_url()
    with pytest.raises(TypeError):
        client.configure(unknown="value")
    with pytest.raises(TypeError):
        client.configure(school="bad")
    with pytest.raises(ValueError):
        client.build_url("other")


def test_transport_and_pacing(monkeypatch):
    requests = []
    sleeps = []

    def transport(request, timeout):
        requests.append((request, timeout))
        return BytesIO(json.dumps({"data": 1}).encode())

    monkeypatch.setattr("schoolmenu.provider.urlopen", transport)
    monkeypatch.setattr("schoolmenu.provider.time.monotonic", lambda: 10)
    monkeypatch.setattr("schoolmenu.provider.time.sleep", sleeps.append)
    client = SchoolCafeClient(request_delay=1, timeout=3)
    assert client.get_weekly_menu("11/9/2026") == {"data": 1}
    assert client.get_daily_menu("11/9/2026") == {"data": 1}
    assert sleeps == [1]
    client.request_delay = 0
    client.get_daily_menu()
    assert sleeps == [1]
    assert requests[0][0].get_header("Accept") == "application/json"
    assert requests[0][1] == 3


@pytest.mark.parametrize("body", [b"invalid", b"\xff", b"[]"])
def test_invalid_response(body, monkeypatch):
    monkeypatch.setattr("schoolmenu.provider.urlopen", lambda *a, **k: BytesIO(body))
    with pytest.raises(ProviderError) as error:
        SchoolCafeClient().get_weekly_menu()
    assert not error.value.retryable


@pytest.mark.parametrize(
    "error,retryable",
    [
        (URLError("dns"), True),
        (TimeoutError(), True),
        (HTTPError("url", 403, "forbidden", {}, None), False),
        (HTTPError("url", 503, "down", {}, None), True),
    ],
)
def test_transport_failures(error, retryable, monkeypatch):
    def transport(*args, **kwargs):
        raise error

    monkeypatch.setattr("schoolmenu.provider.urlopen", transport)
    client = SchoolCafeClient()
    with pytest.raises(ProviderError) as failure:
        client.get_daily_menu()
    assert failure.value.retryable is retryable
    assert client._last_request_at is not None
