from datetime import UTC, date, datetime, timedelta

from schoolmenu.domain import Day, Group, Item
from schoolmenu.ics import (
    _utc_timestamp,
    escape_ical_text,
    fold_ical_line,
)
from schoolmenu.ics import (
    build_calendar as _build_calendar,
)


def make_item(name, *, pe_id=1, preference="neutral", is_related=False, category="ENTREES"):
    return Item(
        source_id=1,
        pe_id=pe_id,
        name=name,
        category=category,
        serving_size="",
        image="",
        allergens="",
        nutrition=[],
        preference=preference,
        is_related_item=is_related,
    )


def make_weeks(start, *, stale=True):
    days = [Day(start + timedelta(days=offset)) for offset in range(5)]
    parent = make_item("Cheese, Pizzable", preference="liked")
    related = make_item("Fruit Cup", pe_id=2, preference="disliked", is_related=True)
    parent.related_items.append(related)
    days[0].groups.append(Group("Entrées", "main", [parent, related]))
    return [
        {
            "days": days,
            "stale": stale,
            "fetched_at": datetime(2026, 11, 9, 12, tzinfo=UTC),
        }
    ]


def build_calendar(weeks, **kwargs):
    return _build_calendar(
        weeks,
        school_key="NORTHEAST_ELEMENTARY",
        menu_base_url="https://menus.example.test/lunchbox",
        **kwargs,
    )


def test_ical_text_escapes_reserved_characters_and_newlines():
    assert escape_ical_text("A\\B, C; D\r\nE") == "A\\\\B\\, C\\; D\\nE"


def test_ical_line_folding_respects_utf8_octet_limit_and_codepoints():
    text = "Résumé 🍲 " * 20
    folded = fold_ical_line("SUMMARY:" + text)
    lines = folded.split("\r\n")

    assert len(lines) > 1
    assert all(len(line.encode("utf-8")) <= 75 for line in lines)
    assert all(line.startswith(" ") for line in lines[1:])
    assert lines[0] + "".join(line[1:] for line in lines[1:]) == "SUMMARY:" + text


def test_calendar_has_ten_stable_all_day_events_with_preferences_and_linked_choices():
    first = make_weeks(date(2026, 11, 9))
    second = make_weeks(date(2026, 11, 16))
    generated_at = datetime(2026, 11, 9, 13, 30, tzinfo=UTC)

    content = build_calendar(
        first + second,
        school_id="3b1df853-0744-4fae-9de7-02ecd78c6e4a",
        school_label="Northeast Elementary",
        grade="01",
        generated_at=generated_at,
    )
    repeated = build_calendar(
        first + second,
        school_id="3b1df853-0744-4fae-9de7-02ecd78c6e4a",
        school_label="Northeast Elementary",
        grade="01",
        generated_at=generated_at,
    )

    assert content == repeated
    assert content.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
    assert "METHOD:PUBLISH\r\n" in content
    assert content.count("BEGIN:VEVENT\r\n") == 10
    assert "SUMMARY:Monday\\, Nov 9 — Northeast Elementary — Grade 01\r\n" in content
    assert "DTSTART;VALUE=DATE:20261109\r\n" in content
    assert "DTEND;VALUE=DATE:20261110\r\n" in content
    unfolded = content.replace("\r\n ", "")
    assert "✅ Cheese\\, Pizzable" in unfolded
    assert "Served together: ❌ Fruit Cup" in unfolded
    assert "[LIKED]" not in unfolded and "[DISLIKED]" not in unfolded
    assert "WARNING: Menu data may be out of date." in unfolded
    assert unfolded.count("Fruit Cup") == 2
    uids = [line for line in content.split("\r\n") if line.startswith("UID:")]
    assert len(uids) == len(set(uids)) == 10
    assert content.endswith("END:VCALENDAR\r\n")


def test_calendar_description_groups_entrees_sides_and_drinks_preserving_relationships():
    entree = make_item("Beef Taco Meat", pe_id=10, preference="liked")
    doritos = make_item(
        "Nacho Cheese Doritos", pe_id=11, preference="disliked", is_related=True, category="GRAINS"
    )
    entree.related_items.append(doritos)
    broccoli = make_item("Steamed Broccoli", pe_id=12, category="VEGETABLE SERVED")
    apples = make_item("Apple Slices", pe_id=13, category="FRUITS")
    white_milk = make_item("1% White Milk", pe_id=14, preference="liked", category="MILK")
    chocolate_milk = make_item("Chocolate Milk", pe_id=15, preference="disliked", category="MILK")
    day = Day(
        date(2026, 11, 9),
        [
            Group("Entrées", "main", [entree, doritos]),
            Group("Vegetables · served", "main", [broccoli]),
            Group("Fruit", "extra", [apples]),
            Group("Drinks", "main", [white_milk, chocolate_milk]),
            Group("Grains", "extra", [doritos]),
        ],
    )
    week = {
        "days": [day],
        "stale": False,
        "fetched_at": datetime(2026, 11, 9, 12, tzinfo=UTC),
    }

    content = build_calendar(
        [week],
        school_id="school-id",
        school_label="Northeast Elementary",
        grade="01",
        generated_at=datetime(2026, 11, 9, 13, 30, tzinfo=UTC),
    )
    unfolded = content.replace("\r\n ", "")
    description = unfolded.split("DESCRIPTION:", 1)[1].split("\r\nEND:VEVENT", 1)[0]

    entree_summary = (
        r"MAIN ENTRÉES\n• ✅ Beef Taco Meat\n"
        r"  ↳ Served together: ❌ Nacho Cheese Doritos"
    )
    assert entree_summary in description
    assert r"🥦 SIDES\n• Steamed Broccoli\n• Apple Slices" in description
    assert r"🥛 MILK & DRINKS\n• ✅ 1% White Milk\n• ❌ Chocolate Milk" in description
    assert description.count("Nacho Cheese Doritos") == 1
    assert "Vegetables · served" not in description
    assert "Grains" not in description


def test_unpublished_day_is_still_a_calendar_event_with_clear_placeholder():
    weeks = make_weeks(date(2026, 11, 9), stale=False)

    content = build_calendar(
        weeks,
        school_id="3b1df853-0744-4fae-9de7-02ecd78c6e4a",
        school_label="Northeast Elementary",
        grade="01",
        generated_at=datetime(2026, 11, 9, 13, 30, tzinfo=UTC),
    )

    assert "SUMMARY:Wednesday\\, Nov 11 — Northeast Elementary — Grade 01\r\n" in content
    unfolded = content.replace("\r\n ", "")
    menu_url = (
        "https://menus.example.test/lunchbox/?week=2026-11-09&school=NORTHEAST_ELEMENTARY&grade=01"
    )
    assert f"URL:{menu_url}" in unfolded
    assert f"DESCRIPTION:No menu published yet.\\n\\n📋 FULL MENU\\n{menu_url}" in unfolded


def test_calendar_text_lines_are_folded_after_escaping():
    long_item = make_item("é" * 100)
    day = Day(date(2026, 11, 9), [Group("Entrées", "main", [long_item])])
    week = {
        "days": [day],
        "stale": False,
        "fetched_at": datetime(2026, 11, 9, 12, tzinfo=UTC),
    }

    content = build_calendar(
        [week],
        school_id="3b1df853-0744-4fae-9de7-02ecd78c6e4a",
        school_label="Northeast Elementary",
        grade="01",
        generated_at=datetime(2026, 11, 9, 13, 30, tzinfo=UTC),
    )

    assert all(len(line.encode("utf-8")) <= 75 for line in content.split("\r\n"))


def test_calendar_window_contains_only_the_next_fourteen_days():
    weeks = [
        *make_weeks(date(2026, 11, 9), stale=False),
        *make_weeks(date(2026, 11, 16), stale=False),
        *make_weeks(date(2026, 11, 23), stale=False),
    ]

    content = build_calendar(
        weeks,
        school_id="3b1df853-0744-4fae-9de7-02ecd78c6e4a",
        school_label="Northeast Elementary",
        grade="01",
        window_start=date(2026, 11, 11),
        generated_at=datetime(2026, 11, 9, 13, 30, tzinfo=UTC),
    )

    event_dates = [
        line.split(":", 1)[1]
        for line in content.split("\r\n")
        if line.startswith("DTSTART;VALUE=DATE:")
    ]
    assert event_dates == [
        "20261111",
        "20261112",
        "20261113",
        "20261116",
        "20261117",
        "20261118",
        "20261119",
        "20261120",
        "20261123",
        "20261124",
    ]


def test_naive_timestamps_are_assumed_to_be_utc():
    assert _utc_timestamp(datetime(2026, 11, 9, 12, 30)) == "20261109T123000Z"


def test_incomplete_menu_groups_and_duplicate_linked_items_are_summarized_once():
    related = make_item("Child Choice", pe_id=21, is_related=True)
    parent = make_item("Parent Entrée", pe_id=20)
    parent.related_items.extend([related, related])
    day = Day(
        date(2026, 11, 9),
        [
            Group("Related only", "side", [related]),
            Group("Lunch", "main", [parent, parent]),
        ],
        incomplete=True,
    )
    week = {
        "days": [day],
        "stale": False,
        "fetched_at": datetime(2026, 11, 9, 12, tzinfo=UTC),
    }

    content = build_calendar(
        [week],
        school_id="3b1df853-0744-4fae-9de7-02ecd78c6e4a",
        school_label="Northeast Elementary",
        grade="01",
    )
    unfolded = content.replace("\r\n ", "")

    assert "WARNING: Some menu information is incomplete." in unfolded
    assert "Related only" not in unfolded
    assert unfolded.count("Parent Entrée") == 1
    assert unfolded.count("Child Choice") == 1
