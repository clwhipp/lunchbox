import json
import re
from datetime import date
from pathlib import Path

import pytest
from playwright.sync_api import expect

from schoolmenu import services
from tests.conftest import SAMPLES

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.mark.parametrize("day", [7, 8])
def test_weekend_opens_upcoming_week(page, menu_server, monkeypatch, day):
    monkeypatch.setattr(services.timezone, "localdate", lambda: date(2026, 11, day))
    page.goto(menu_server)
    expect(page.get_by_role("heading", name="Nov 9 – Nov 13, 2026")).to_be_visible()
    page.get_by_role("link", name="Previous week", exact=True).click()
    expect(page).to_have_url(re.compile("week=2026-11-02"))
    page.get_by_role("link", name="Upcoming week", exact=True).click()
    expect(page).to_have_url(re.compile("week=2026-11-09"))


def test_week_navigation_and_modal(page, menu_server):
    page.goto(menu_server)
    expect(page.locator(".day-column")).to_have_count(5)
    expect(page.get_by_role("heading", name="Nov 9 – Nov 13, 2026")).to_be_visible()
    page.get_by_role("link", name="Next week", exact=True).click()
    expect(page).to_have_url(re.compile("week=2026-11-16"))
    expect(page.locator(".empty-day")).to_have_count(5)
    page.go_back()
    page.get_by_role("link", name="Previous week", exact=True).click()
    expect(page).to_have_url(re.compile("week=2026-11-02"))
    page.locator("#week-date").fill("2026-11-04")
    page.get_by_role("button", name="Go", exact=True).click()
    expect(page).to_have_url(re.compile("week=2026-11-02"))
    page.get_by_role("link", name="This week", exact=True).click()
    opener = page.get_by_role("link", name=re.compile("Cheese Pizzable"))
    opener.click()
    expect(page.get_by_role("dialog")).to_be_visible()
    expect(page.get_by_role("heading", name="Cheese Pizzable", exact=True)).to_be_visible()
    expect(page.locator(".nutrition")).to_contain_text("674.63 mg")
    expect(page.locator(".allergen-box")).to_contain_text("May contain Soy")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).not_to_be_visible()
    expect(opener).to_be_focused()


def test_served_together_choice_is_indented_under_parent_entree(page, menu_server, monkeypatch):
    payload = json.loads((SAMPLES / "weekly-2026-11-09.json").read_text())
    monday = payload["11/9/2026"]
    entree = monday["ENTREES"][0]
    choice = monday["VEGETABLES CHOICE BAR"][0]
    payload["_served_together"] = {"11/9/2026": [[entree["PEMenuItemId"], choice["PEMenuItemId"]]]}
    monkeypatch.setattr(services, "fetch_provider", lambda *args: payload)

    page.goto(menu_server)

    parent = page.locator(".menu-item-entry").filter(has_text=entree["MenuItemDescription"])
    expect(parent.locator(".related-items")).to_contain_text(choice["MenuItemDescription"])
    expect(page.get_by_role("link", name=re.compile(choice["MenuItemDescription"]))).to_have_count(
        1
    )
    page.set_viewport_size({"width": 320, "height": 1000})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    expect(parent.locator(".related-items")).to_be_visible()


def test_capture_lunch_planning_feature_screenshots(page, menu_server, monkeypatch):
    payload = json.loads((SAMPLES / "weekly-2026-11-09.json").read_text())
    tuesday = payload["11/10/2026"]
    entree = next(
        row for row in tuesday["ENTREES"] if row["MenuItemDescription"] == "Beef Taco Meat"
    )
    choice = next(
        row for row in tuesday["GRAINS"] if row["MenuItemDescription"] == "Nacho Cheese Doritos"
    )
    payload["_served_together"] = {"11/10/2026": [[entree["PEMenuItemId"], choice["PEMenuItemId"]]]}
    monkeypatch.setattr(services, "fetch_provider", lambda *args: payload)
    services.save_sack_lunch(
        services.Selection.parse(
            {"week": "2026-11-09", "school": "NORTHEAST_ELEMENTARY", "grade": "01"}
        ),
        date(2026, 11, 9),
        True,
    )
    screenshots = Path("docs/screenshots")
    screenshots.mkdir(parents=True, exist_ok=True)

    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto(menu_server)
    expect(
        page.get_by_role("checkbox", name="Sack lunch for Monday, November 9", exact=True)
    ).to_be_checked()
    expect(page.locator(".sack-summary")).to_contain_text("Mon, Nov 9")
    linked_item = page.locator("#day-2026-11-10 .menu-item-entry").filter(has_text="Beef Taco Meat")
    expect(linked_item.locator(".related-items")).to_contain_text("Nacho Cheese Doritos")
    page.screenshot(path=str(screenshots / "weekly-menu-desktop.png"), full_page=True)

    page.set_viewport_size({"width": 390, "height": 1280})
    page.goto(menu_server)
    expect(
        page.get_by_role("checkbox", name="Sack lunch for Monday, November 9", exact=True)
    ).to_be_checked()
    page.screenshot(path=str(screenshots / "mobile-menu.png"))
    linked_item.screenshot(path=str(screenshots / "served-together-choice-mobile.png"))


def test_sack_lunch_summary_and_new_browser_context(page, browser, menu_server):
    page.goto(menu_server)
    tuesday = page.get_by_role("checkbox", name="Sack lunch for Tuesday, November 10", exact=True)
    tuesday.check()
    expect(tuesday).to_be_checked()
    expect(page.locator(".sack-summary strong")).to_contain_text("1 day")
    expect(page.locator(".sack-summary")).to_contain_text("Tue, Nov 10")
    expect(page.locator(".sack-summary")).not_to_contain_text("Mon, Nov 9")
    page.locator('select[name="grade"]').select_option("02")
    page.get_by_role("button", name="Apply", exact=True).click()
    tuesday = page.get_by_role("checkbox", name="Sack lunch for Tuesday, November 10", exact=True)
    expect(tuesday).to_be_checked()
    expect(page.locator(".sack-summary")).to_contain_text("Tue, Nov 10")
    tuesday.uncheck()
    expect(page.locator(".sack-summary")).to_contain_text("No sack lunches confirmed.")
    page.get_by_role("checkbox", name="Sack lunch for Wednesday, November 11", exact=True).check()
    page.reload()
    expect(
        page.get_by_role("checkbox", name="Sack lunch for Wednesday, November 11", exact=True)
    ).to_be_checked()
    fresh = browser.new_context()
    try:
        other = fresh.new_page()
        other.goto(menu_server)
        expect(
            other.get_by_role("checkbox", name="Sack lunch for Wednesday, November 11", exact=True)
        ).to_be_checked()
        expect(other.locator(".sack-summary")).to_contain_text("Wed, Nov 11")
    finally:
        fresh.close()


def test_disliked_foods_can_be_compacted_and_restored(page, menu_server):
    page.goto(menu_server)
    toggle = page.get_by_role("checkbox", name="Compact disliked items", exact=True)
    expect(toggle).to_be_checked()

    first_dislike = page.get_by_role(
        "checkbox", name="Dislikes Cheese Pizzable on Monday", exact=True
    )
    first_card = page.locator(".food-card").filter(
        has=page.get_by_role("link", name=re.compile("Cheese Pizzable"))
    )
    first_photo = first_card.locator(".food-photo")
    first_like = page.get_by_role("checkbox", name="Likes Cheese Pizzable on Monday", exact=True)
    first_dislike.check()
    expect(first_card).to_have_class(re.compile(r"\bdisliked\b"))
    expect(first_photo).to_be_hidden()
    expect(first_card.get_by_role("link")).to_be_visible()
    expect(first_dislike).to_be_visible()
    expect(first_like).to_be_hidden()

    toggle.uncheck()
    expect(first_photo).to_be_visible()
    second_dislike = page.get_by_role(
        "checkbox", name="Dislikes Cheeseburger on Monday", exact=True
    )
    second_card = page.locator(".food-card").filter(
        has=page.get_by_role("link", name=re.compile("Cheeseburger"))
    )
    second_photo = second_card.locator(".food-photo")
    second_dislike.check()
    expect(toggle).not_to_be_checked()
    expect(second_photo).to_be_visible()

    toggle.check()
    expect(first_photo).to_be_hidden()
    expect(second_photo).to_be_hidden()
    first_dislike.uncheck()
    expect(first_photo).to_be_visible()
    expect(first_card).to_have_class(re.compile(r"\bneutral\b"))
    page.reload()
    expect(page.get_by_role("checkbox", name="Compact disliked items", exact=True)).to_be_checked()


def test_failed_save_rolls_back_checkbox(page, menu_server):
    page.goto(menu_server)
    page.route("**/preference/", lambda route: route.fulfill(status=503, body="Unavailable"))
    box = page.get_by_role("checkbox", name="Likes Cheeseburger on Monday", exact=True)
    # A fast failed response can undo the click before check() verifies the state.
    box.click()
    expect(page.get_by_role("status")).to_contain_text("Could not save")
    expect(box).not_to_be_checked()
    expect(box).to_be_enabled()
    expect(page.locator("#save-status")).to_have_text("", timeout=7000)


@pytest.mark.parametrize("width", [320, 768, 1440])
def test_responsive_menu_has_no_horizontal_overflow(page, menu_server, width):
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(menu_server)
    expect(page.locator(".day-column")).to_have_count(5)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    if width == 320:
        expect(page.locator(".summary-card")).to_have_count(1)
        expect(
            page.get_by_role("checkbox", name="Sack lunch for Monday, November 9", exact=True)
        ).to_be_visible()
        assert (
            page.locator(".sack-lunch-toggle").first.evaluate(
                "el => el.getBoundingClientRect().height"
            )
            >= 42
        )
    if width == 1440:
        Path("artifacts").mkdir(exist_ok=True)
        page.screenshot(path="artifacts/weekly-desktop.png", full_page=True)
    if width == 320:
        Path("artifacts").mkdir(exist_ok=True)
        page.screenshot(path="artifacts/weekly-mobile.png", full_page=True)


@pytest.mark.parametrize("before_init", [False, True])
def test_broken_image_fallback(page, menu_server, before_init):
    if before_init:
        page.route(
            "**/bootstrap.js",
            lambda route: route.fulfill(
                content_type="text/javascript",
                body='import { init } from "./app.js"; window.initMenu = () => init(document);',
            ),
        )
    page.route(
        "**/thumbnail/",
        lambda route: route.fulfill(status=404, body="missing"),
    )
    page.goto(menu_server)
    burger = page.locator(".food-card").filter(
        has=page.get_by_role("link", name="Cheeseburger 1 ea.", exact=True)
    )
    burger.scroll_into_view_if_needed()
    if before_init:
        expect(page.locator("body")).not_to_have_class(re.compile(r"\bjs-enabled\b"))
        page.wait_for_function(
            "img => img.complete && img.naturalWidth === 0",
            arg=burger.locator("img").element_handle(),
        )
        page.evaluate("window.initMenu()")
    expect(burger.locator("img")).to_have_attribute("src", re.compile("plate.svg$"))


@pytest.mark.browser_context_args(java_script_enabled=False)
def test_plain_html_without_javascript(page, menu_server):
    page.goto(menu_server)
    sack_box = page.get_by_role("checkbox", name="Sack lunch for Monday, November 9", exact=True)
    sack_box.check()
    page.get_by_role("button", name="Save sack lunch for Monday, November 9", exact=True).click()
    expect(sack_box).to_be_checked()
    expect(page.locator(".sack-summary")).to_contain_text("Mon, Nov 9")
    card = page.locator(".food-card").filter(
        has=page.get_by_role("link", name="Cheeseburger 1 ea.", exact=True)
    )
    card.get_by_role("button", name="Like", exact=True).click()
    expect(card).to_have_attribute("data-preference", "liked")
    card.get_by_role("link").click()
    expect(page.get_by_role("heading", name="Cheeseburger", exact=True)).to_be_visible()
    expect(page.locator(".nutrition")).to_contain_text("Sodium")
