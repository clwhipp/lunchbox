from datetime import date

from schoolmenu.calendar_feed import calendar_week_starts


def test_prefetch_weeks_overlap_exactly_the_next_fourteen_day_window():
    assert calendar_week_starts(date(2026, 11, 11)) == (
        date(2026, 11, 9),
        date(2026, 11, 16),
        date(2026, 11, 23),
    )
    assert calendar_week_starts(date(2026, 11, 7)) == (
        date(2026, 11, 9),
        date(2026, 11, 16),
    )
    assert calendar_week_starts(date(2026, 11, 8)) == (
        date(2026, 11, 9),
        date(2026, 11, 16),
    )
    assert calendar_week_starts(date(2026, 11, 13)) == (
        date(2026, 11, 9),
        date(2026, 11, 16),
        date(2026, 11, 23),
    )
