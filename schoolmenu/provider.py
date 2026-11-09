"""Small, dependency-free client for SchoolCafe's public menu endpoints."""

from __future__ import annotations

import json
import time
from datetime import date
from enum import Enum
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class School(Enum):
    ABBIE_GROVE = "e60dafbf-50ae-417b-9aa8-7b7d7e7a730e"
    ANKENY_HIGH_SCHOOL = "15e05324-b848-4571-a262-a4d3c1daa4e1"
    ASHLAND_RIDGE = "158e0e52-6325-447b-bae7-5261ab14d634"
    CENTENNIAL_HIGH_SCHOOL = "1b8e3383-98e6-48ce-bcf1-d0b4db80d4eb"
    CROCKER_ELEMENTARY = "17f18479-4718-4d8f-a838-6789d4fb41b3"
    EAST_ELEMENTARY = "0d431703-7946-4b14-9a14-bb01af4903f4"
    HERITAGE_ELEMENTARY = "29786f7a-18af-4840-832d-7e3097933c4d"
    NORTHEAST_ELEMENTARY = "3b1df853-0744-4fae-9de7-02ecd78c6e4a"
    NORTHVIEW_MIDDLE_SCHOOL = "94aaedd1-e4c9-4d33-a7a8-55e12337f163"
    NORTHWEST_ELEMENTARY = "25a5872a-63ca-4e49-8943-6952b1cbe520"
    PARKVIEW_MIDDLE_SCHOOL = "42623c6c-2613-4293-995b-4ec18259ec54"
    PRAIRIE_RIDGE_MIDDLE_SCHOOL = "9efa105f-53ff-4e3e-b0fa-4a904ef005b6"
    PRAIRIE_TRAIL_ELEMENTARY = "b4a627df-67b5-4b5c-8cc3-5685d6b4ce74"
    ROCK_CREEK_ELEMENTARY = "380d5609-3fd4-44c7-8d97-ff9737c32404"
    SOUTHEAST_ELEMENTARY = "bf718232-898c-4fef-a332-4233ea041bbc"
    SOUTHVIEW_MIDDLE_SCHOOL = "9a0dcaea-8928-4bc6-be2d-79ec44455db4"
    WESTWOOD_ELEMENTARY = "fd7f6474-9413-4e36-b420-632c63e7909b"


class ProviderError(RuntimeError):
    """An upstream failure, classified for bounded retries."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class SchoolCafeClient:
    """Retrieve SchoolCafe daily or weekly menus for a selected school/grade."""

    BASE_URL = "https://webapis.schoolcafe.com/api/CalendarView"
    SCHOOLS = {school: school.value for school in School}
    DEFAULT_SCHOOL = School.NORTHEAST_ELEMENTARY
    DEFAULT_SCHOOL_ID = SCHOOLS[DEFAULT_SCHOOL]
    DEFAULT_GRADE = "01"
    _CONFIGURABLE = {
        "school",
        "serving_date",
        "serving_line",
        "meal_type",
        "grade",
        "person_id",
        "enabled_weekend_menus",
    }

    def __init__(
        self,
        *,
        school: School = DEFAULT_SCHOOL,
        serving_date: str | None = None,
        serving_line: str = "A Line",
        meal_type: str = "Lunch",
        grade: str = DEFAULT_GRADE,
        person_id: str | None = None,
        enabled_weekend_menus: bool = False,
        request_delay: float = 1.0,
        timeout: float = 30.0,
    ) -> None:
        if request_delay < 0:
            raise ValueError("request_delay cannot be negative")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if not isinstance(school, School):
            raise TypeError("school must be a School enum value")
        self.school = school
        self.school_id = self.SCHOOLS[school]
        today = date.today()
        self.serving_date = serving_date or f"{today.month}/{today.day}/{today.year}"
        self.serving_line = serving_line
        self.meal_type = meal_type
        self.grade = grade
        self.person_id = person_id
        self.enabled_weekend_menus = enabled_weekend_menus
        self.request_delay = request_delay
        self.timeout = timeout
        self._last_request_at: float | None = None
        self._request_lock = Lock()

    def configure(self, **values: Any) -> None:
        """Change one or more request values for future calls."""
        unknown = set(values) - self._CONFIGURABLE
        if unknown:
            names = ", ".join(sorted(unknown))
            raise TypeError(f"unknown configuration value(s): {names}")
        if "school" in values:
            school = values["school"]
            if not isinstance(school, School):
                raise TypeError("school must be a School enum value")
            self.school = school
            self.school_id = self.SCHOOLS[school]
            del values["school"]
        for key, value in values.items():
            setattr(self, key, value)

    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)

    def build_url(self, endpoint: str, serving_date: str | None = None) -> str:
        """Build a daily or weekly API URL without sending a request."""
        if endpoint not in {"Daily", "Weekly"}:
            raise ValueError("endpoint must be 'Daily' or 'Weekly'")
        date_value = self.serving_date if serving_date is None else serving_date
        params = {
            "SchoolId": self.school_id,
            "ServingDate": date_value,
            "ServingLine": self.serving_line,
            "MealType": self.meal_type,
            "Grade": self.grade,
            "PersonId": self._as_text(self.person_id),
        }
        if endpoint == "Weekly":
            params["enabledWeekendMenus"] = self._as_text(self.enabled_weekend_menus)
        query = urlencode(params)
        return f"{self.BASE_URL}/Get{endpoint}MenuitemsByGrade?{query}"

    def build_daily_url(self, serving_date: str | None = None) -> str:
        return self.build_url("Daily", serving_date)

    def build_weekly_url(self, serving_date: str | None = None) -> str:
        return self.build_url("Weekly", serving_date)

    def _get_json(self, url: str) -> dict[str, Any]:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "SchoolCafeMenuClient/1.0",
            },
        )
        with self._request_lock:
            if self._last_request_at is not None:
                elapsed = time.monotonic() - self._last_request_at
                wait = self.request_delay - elapsed
                if wait > 0:
                    time.sleep(wait)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
            except HTTPError as exc:
                raise ProviderError(
                    f"SchoolCafe returned HTTP {exc.code}",
                    retryable=exc.code in {500, 502, 503, 504},
                ) from exc
            except (URLError, TimeoutError) as exc:
                raise ProviderError("Could not reach SchoolCafe", retryable=True) from exc
            finally:
                self._last_request_at = time.monotonic()

        try:
            result = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("SchoolCafe returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise ProviderError("Expected a JSON object from SchoolCafe")
        return result

    def get_daily_menu(self, serving_date: str | None = None) -> dict[str, Any]:
        """Fetch one day's menu; date format is M/D/YYYY, e.g. 11/9/2026."""
        return self._get_json(self.build_daily_url(serving_date))

    def get_weekly_menu(self, serving_date: str | None = None) -> dict[str, Any]:
        """Fetch five dates starting at serving_date; pass Monday for a school week."""
        return self._get_json(self.build_weekly_url(serving_date))
