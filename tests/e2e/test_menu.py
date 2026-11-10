import re
from datetime import date
from pathlib import Path

import pytest
from playwright.sync_api import expect

from schoolmenu import services

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


def test_preferences_summary_and_new_browser_context(page, browser, menu_server):
    page.goto(menu_server)
    chicken = page.get_by_role("checkbox", name="Likes Popcorn Chicken on Tuesday", exact=True)
    chicken.check()
    expect(chicken).to_be_checked()
    expect(page.locator(".food-card.liked")).to_have_count(2)
    expect(page.locator(".school-summary strong")).to_contain_text("2 days")
    chicken.uncheck()
    expect(page.locator(".food-card.liked")).to_have_count(0)
    for name in ["Cheese Pizzable", "Cheeseburger", "Hamburger on a Bun"]:
        box = page.get_by_role("checkbox", name=f"Dislikes {name} on Monday", exact=True)
        box.check()
        expect(box).to_be_checked()
        expect(box).to_be_enabled()
    expect(page.locator(".pack-summary strong")).to_contain_text("1 day")
    expect(page.locator(".pack-summary")).to_contain_text("Mon, Nov 9")
    page.reload()
    expect(page.locator(".food-card.disliked")).to_have_count(3)
    fresh = browser.new_context()
    try:
        other = fresh.new_page()
        other.goto(menu_server)
        expect(other.locator(".food-card.disliked")).to_have_count(3)
        expect(other.locator(".pack-summary strong")).to_contain_text("1 day")
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
    box.check()
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
    if width == 1440:
        Path("artifacts").mkdir(exist_ok=True)
        page.screenshot(path="artifacts/weekly-desktop.png", full_page=True)
    if width == 320:
        Path("artifacts").mkdir(exist_ok=True)
        page.screenshot(path="artifacts/weekly-mobile.png", full_page=True)


def test_broken_image_fallback(page, menu_server):
    page.route(
        "**/thumbnail/",
        lambda route: route.fulfill(status=404, body="missing"),
    )
    page.goto(menu_server)
    burger = page.locator(".food-card").filter(
        has=page.get_by_role("link", name="Cheeseburger 1 ea.", exact=True)
    )
    burger.scroll_into_view_if_needed()
    expect(burger.locator("img")).to_have_attribute("src", re.compile("plate.svg$"))


def test_plain_html_without_javascript(browser, menu_server):
    context = browser.new_context(java_script_enabled=False)
    try:
        page = context.new_page()
        page.goto(menu_server)
        card = page.locator(".food-card").filter(
            has=page.get_by_role("link", name="Cheeseburger 1 ea.", exact=True)
        )
        card.get_by_role("button", name="Like", exact=True).click()
        expect(card).to_have_attribute("data-preference", "liked")
        card.get_by_role("link").click()
        expect(page.get_by_role("heading", name="Cheeseburger", exact=True)).to_be_visible()
        expect(page.locator(".nutrition")).to_contain_text("Sodium")
    finally:
        context.close()
