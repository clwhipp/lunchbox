import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { JSDOM } from "jsdom";
import { init } from "../../schoolmenu/static/menus/app.js";

describe("menu progressive enhancement", () => {
  let doc, win, form, like, dislike, dialog, calendarDialog;
  function fire(name, detail) {
    doc.dispatchEvent(new win.CustomEvent(name, { detail }));
  }
  beforeEach(() => {
    vi.useFakeTimers();
    win = new JSDOM(
      `<body><div id="save-status"></div><dialog id="food-dialog"><button data-close-dialog>Close</button><div id="dialog-content"></div></dialog><dialog id="calendar-dialog"></dialog><div id="week-panel"><label><input id="compact-disliked" type="checkbox" checked>Compact disliked items</label><a data-food-detail href="/food">Food</a><form class="preference-form" data-saved-state="neutral"><input type="hidden" name="state" value="neutral"><input type="checkbox" id="like" value="liked"><input type="checkbox" id="dislike" value="disliked"><button name="state" value="liked">Like</button><button name="state" value="neutral">Clear</button></form></div><input id="other" type="date"><img id="photo" src="broken" data-fallback="/plate.svg"></body>`,
      { url: "http://localhost" },
    ).window;
    doc = win.document;
    form = doc.querySelector("form");
    form.requestSubmit = vi.fn();
    like = doc.getElementById("like");
    dislike = doc.getElementById("dislike");
    dialog = doc.getElementById("food-dialog");
    dialog.showModal = vi.fn();
    dialog.close = vi.fn(() => dialog.dispatchEvent(new win.Event("close")));
    calendarDialog = doc.getElementById("calendar-dialog");
    calendarDialog.showModal = vi.fn();
    calendarDialog.close = vi.fn(() =>
      calendarDialog.dispatchEvent(new win.Event("close")),
    );
    init(doc);
  });
  afterEach(() => {
    vi.useRealTimers();
    win.close();
  });
  it("syncs the currently selected school and grade into the calendar details", () => {
    const settings = doc.createElement("form");
    settings.className = "school-settings";
    settings.innerHTML =
      '<select name="school"><option value="NORTHEAST_ELEMENTARY">Northeast Elementary</option><option value="ABBIE_GROVE">Abbie Grove</option></select><select name="grade"><option value="01">01</option><option value="02">02</option></select>';
    const reveal = doc.createElement("form");
    reveal.className = "calendar-reveal-form";
    reveal.innerHTML =
      '<input type="hidden" name="school"><input type="hidden" name="grade">';
    const schoolLabel = doc.createElement("span");
    schoolLabel.id = "calendar-school-label";
    const gradeLabel = doc.createElement("span");
    gradeLabel.id = "calendar-grade-label";
    calendarDialog.append(reveal, schoolLabel, gradeLabel);
    doc.body.append(settings);

    const school = settings.querySelector('select[name="school"]');
    const grade = settings.querySelector('select[name="grade"]');
    school.value = "ABBIE_GROVE";
    school.dispatchEvent(new win.Event("change", { bubbles: true }));
    grade.value = "02";
    grade.dispatchEvent(new win.Event("change", { bubbles: true }));

    expect(reveal.querySelector('input[name="school"]').value).toBe(
      "ABBIE_GROVE",
    );
    expect(reveal.querySelector('input[name="grade"]').value).toBe("02");
    expect(schoolLabel.textContent).toBe("Abbie Grove");
    expect(gradeLabel.textContent).toBe("02");
  });
  it("opens the calendar dialog and restores focus after closing", () => {
    const trigger = doc.createElement("button");
    trigger.dataset.calendarDialogOpen = "";
    doc.body.append(trigger);

    const click = new win.MouseEvent("click", {
      bubbles: true,
      cancelable: true,
    });
    trigger.dispatchEvent(click);

    expect(click.defaultPrevented).toBe(true);
    expect(calendarDialog.showModal).toHaveBeenCalledOnce();
    calendarDialog.dispatchEvent(new win.Event("close"));
    expect(doc.activeElement).toBe(trigger);

    calendarDialog.setAttribute("open", "");
    const alreadyOpen = new win.MouseEvent("click", {
      bubbles: true,
      cancelable: true,
    });
    trigger.dispatchEvent(alreadyOpen);
    expect(alreadyOpen.defaultPrevented).toBe(true);
    expect(calendarDialog.showModal).toHaveBeenCalledOnce();
    calendarDialog.dispatchEvent(new win.Event("close"));
    expect(doc.activeElement).toBe(trigger);
  });
  it("reopens a revealed calendar dialog as a modal", () => {
    const revealed = new JSDOM(
      '<body><div id="save-status"></div><dialog id="food-dialog"></dialog><dialog id="calendar-dialog" open></dialog></body>',
      { url: "http://localhost" },
    );
    const revealedDialog =
      revealed.window.document.getElementById("calendar-dialog");
    revealedDialog.close = vi.fn(() => {
      revealedDialog.removeAttribute("open");
      revealedDialog.dispatchEvent(new revealed.window.Event("close"));
    });
    revealedDialog.showModal = vi.fn();

    init(revealed.window.document);

    expect(revealedDialog.close).toHaveBeenCalledOnce();
    expect(revealedDialog.showModal).toHaveBeenCalledOnce();
    revealed.window.close();
  });
  it("copies a revealed calendar URL with the clipboard API", async () => {
    const field = doc.createElement("textarea");
    field.id = "calendar-subscription-url";
    field.value = "https://example.test/calendar/short-token.ics";
    const copyStatus = doc.createElement("p");
    copyStatus.id = "calendar-copy-status";
    const button = doc.createElement("button");
    button.dataset.copyCalendarUrl = "";
    doc.body.append(field, copyStatus, button);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(win.navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    button.click();
    await vi.waitFor(() =>
      expect(copyStatus.textContent).toBe("Subscription URL copied."),
    );
    expect(writeText).toHaveBeenCalledWith(field.value);
  });
  it("uses the selection fallback when clipboard access is unavailable", () => {
    const field = doc.createElement("textarea");
    field.id = "calendar-subscription-url";
    field.value = "short-link";
    const copyStatus = doc.createElement("p");
    copyStatus.id = "calendar-copy-status";
    const button = doc.createElement("button");
    button.dataset.copyCalendarUrl = "";
    doc.body.append(field, copyStatus, button);
    Object.defineProperty(win.navigator, "clipboard", {
      configurable: true,
      value: undefined,
    });
    doc.execCommand = vi.fn(() => true);

    button.click();

    expect(doc.execCommand).toHaveBeenCalledWith("copy");
    expect(copyStatus.textContent).toBe("Subscription URL copied.");
  });
  it("selects the URL if the clipboard fallback is blocked", () => {
    const field = doc.createElement("textarea");
    field.id = "calendar-subscription-url";
    field.value = "short-link";
    const copyStatus = doc.createElement("p");
    copyStatus.id = "calendar-copy-status";
    const button = doc.createElement("button");
    button.dataset.copyCalendarUrl = "";
    doc.body.append(field, copyStatus, button);
    Object.defineProperty(win.navigator, "clipboard", {
      configurable: true,
      value: undefined,
    });
    doc.execCommand = vi.fn(() => false);

    button.click();

    expect(copyStatus.textContent).toBe(
      "Copy unavailable; the URL is selected for copying.",
    );
    expect(field.selectionStart).toBe(0);
    expect(field.selectionEnd).toBe(field.value.length);
  });
  it("ignores an orphaned calendar copy button", () => {
    const button = doc.createElement("button");
    button.dataset.copyCalendarUrl = "";
    doc.body.append(button);

    button.click();

    expect(doc.getElementById("calendar-copy-status")).toBe(null);
  });
  it("compacts disliked foods by default and keeps the choice after week swaps", () => {
    const toggle = doc.getElementById("compact-disliked");
    expect(doc.body.classList.contains("compact-disliked")).toBe(true);
    expect(toggle.checked).toBe(true);

    toggle.checked = false;
    toggle.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(doc.body.classList.contains("compact-disliked")).toBe(false);
    expect(win.localStorage.getItem("lunchbox.compactDisliked")).toBe("false");

    const panel = doc.getElementById("week-panel");
    panel.innerHTML =
      '<label><input id="compact-disliked" type="checkbox" checked>Compact disliked items</label>';
    fire("htmx:afterSwap", { target: panel });
    expect(doc.getElementById("compact-disliked").checked).toBe(false);
    panel.innerHTML = "";
    fire("htmx:afterSwap", { target: panel });
  });
  it("loads a previously disabled preference", () => {
    const stored = new JSDOM(
      '<body><div id="save-status"></div><dialog id="food-dialog"></dialog><div id="week-panel"><input id="compact-disliked" type="checkbox" checked></div></body>',
      { url: "http://localhost" },
    );
    stored.window.localStorage.setItem("lunchbox.compactDisliked", "false");
    init(stored.window.document);
    expect(
      stored.window.document.body.classList.contains("compact-disliked"),
    ).toBe(false);
    expect(
      stored.window.document.getElementById("compact-disliked").checked,
    ).toBe(false);
    stored.window.close();
  });
  it("keeps menu controls usable when browser storage is blocked", () => {
    const blocked = new JSDOM(
      '<body><div id="save-status"></div><dialog id="food-dialog"></dialog><div id="week-panel"><input id="compact-disliked" type="checkbox" checked></div></body>',
      { url: "http://localhost" },
    );
    Object.defineProperty(blocked.window, "localStorage", {
      configurable: true,
      get() {
        throw new Error("Storage blocked");
      },
    });
    const blockedDoc = blocked.window.document;
    init(blockedDoc);
    const toggle = blockedDoc.getElementById("compact-disliked");
    expect(blockedDoc.body.classList.contains("compact-disliked")).toBe(true);
    toggle.checked = false;
    toggle.dispatchEvent(new blocked.window.Event("change", { bubbles: true }));
    expect(blockedDoc.body.classList.contains("compact-disliked")).toBe(false);
    blocked.window.close();
  });
  it("selects one preference, switches, and clears", () => {
    like.checked = true;
    like.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(form.querySelector('input[name="state"]').value).toBe("liked");
    expect(dislike.checked).toBe(false);
    dislike.checked = true;
    dislike.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(form.querySelector('input[name="state"]').value).toBe("disliked");
    expect(like.checked).toBe(false);
    dislike.checked = false;
    dislike.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(form.querySelector('input[name="state"]').value).toBe("neutral");
    expect(form.requestSubmit).toHaveBeenCalledTimes(3);
    doc
      .getElementById("other")
      .dispatchEvent(new win.Event("change", { bubbles: true }));
    form
      .querySelector('input[name="state"]')
      .dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(form.requestSubmit).toHaveBeenCalledTimes(3);
  });
  it("disables writes while pending, restores focus, and announces success", () => {
    like.checked = true;
    like.dispatchEvent(new win.Event("change", { bubbles: true }));
    fire("htmx:beforeRequest", { elt: form });
    expect(like.disabled).toBe(true);
    expect(doc.getElementById("save-status").textContent).toBe("Saving…");
    fire("htmx:afterSwap", { target: doc.getElementById("week-panel") });
    fire("htmx:afterRequest", { elt: form, successful: true });
    fire("htmx:afterSwap", { target: doc.getElementById("week-panel") });
    expect(like.disabled).toBe(false);
    expect(doc.activeElement).toBe(like);
    expect(doc.getElementById("save-status").textContent).toBe("Saved.");
    vi.advanceTimersByTime(2500);
    expect(doc.getElementById("save-status").textContent).toBe("");
    like.remove();
    fire("htmx:afterSwap", { target: doc.getElementById("week-panel") });
  });
  it("restores the saved preference after a failed write", () => {
    form.dataset.savedState = "disliked";
    like.checked = true;
    fire("htmx:afterRequest", { elt: form, successful: false });
    expect(like.checked).toBe(false);
    expect(dislike.checked).toBe(true);
    expect(doc.getElementById("save-status").textContent).toContain(
      "Could not save",
    );
    vi.advanceTimersByTime(4999);
    expect(doc.getElementById("save-status").textContent).toContain(
      "Could not save",
    );
    vi.advanceTimersByTime(1);
    expect(doc.getElementById("save-status").textContent).toBe("");
  });
  it("submits sack-lunch changes and restores the prior choice after failure", () => {
    const sack = doc.createElement("form");
    sack.className = "sack-lunch-form";
    sack.dataset.savedState = "false";
    sack.innerHTML = '<input type="checkbox" id="sack" value="true">';
    doc.getElementById("week-panel").append(sack);
    sack.requestSubmit = vi.fn();
    const checkbox = sack.querySelector("input");

    checkbox.checked = true;
    checkbox.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(sack.requestSubmit).toHaveBeenCalledOnce();
    fire("htmx:beforeRequest", { elt: sack });
    expect(checkbox.disabled).toBe(true);
    fire("htmx:afterRequest", { elt: sack, successful: false });
    expect(checkbox.disabled).toBe(false);
    expect(checkbox.checked).toBe(false);
    expect(doc.getElementById("save-status").textContent).toContain(
      "Could not save",
    );
  });
  it("opens and closes details and restores the opener", () => {
    const opener = doc.querySelector("a");
    dialog.dispatchEvent(new win.Event("close"));
    opener.addEventListener("click", (e) => e.preventDefault());
    opener.click();
    fire("htmx:beforeRequest", { elt: opener });
    fire("htmx:afterSwap", { target: doc.getElementById("dialog-content") });
    expect(dialog.showModal).toHaveBeenCalledOnce();
    doc.querySelector("[data-close-dialog]").click();
    expect(dialog.close).toHaveBeenCalledOnce();
    expect(doc.activeElement).toBe(opener);
    opener.remove();
    dialog.dispatchEvent(new win.Event("close"));
    doc.body.click();
  });
  it("handles detail failures and unrelated swaps", () => {
    fire("htmx:afterRequest", {
      elt: doc.querySelector("a"),
      successful: true,
    });
    expect(doc.getElementById("save-status").textContent).toBe("");
    fire("htmx:afterRequest", {
      elt: doc.querySelector("a"),
      successful: false,
    });
    expect(doc.getElementById("save-status").textContent).toContain(
      "Could not load",
    );
    vi.advanceTimersByTime(5000);
    expect(doc.getElementById("save-status").textContent).toBe("");
    fire("htmx:afterSwap", { target: doc.getElementById("week-panel") });
    fire("htmx:afterSwap", { target: doc.body });
    expect(dialog.showModal).not.toHaveBeenCalled();
  });
  it("replaces a broken image exactly once", () => {
    const photo = doc.getElementById("photo");
    photo.dispatchEvent(new win.Event("error"));
    expect(photo.src).toBe("http://localhost/plate.svg");
    expect(photo.hasAttribute("data-fallback")).toBe(false);
    photo.dispatchEvent(new win.Event("error"));
    doc.dispatchEvent(new win.Event("error"));
    expect(photo.src).toBe("http://localhost/plate.svg");
  });
  it("recovers images that failed before initialization and preserves healthy or pending images", () => {
    const early = new JSDOM(
      '<body><div id="save-status"></div><dialog id="food-dialog"></dialog><img id="broken" src="broken" data-fallback="/plate.svg"><img id="loaded" src="loaded" data-fallback="/plate.svg"><img id="pending" src="pending" data-fallback="/plate.svg"></body>',
      { url: "http://localhost" },
    );
    const earlyDoc = early.window.document;
    const broken = earlyDoc.getElementById("broken");
    const loaded = earlyDoc.getElementById("loaded");
    const pending = earlyDoc.getElementById("pending");
    Object.defineProperty(broken, "complete", { value: true });
    Object.defineProperties(loaded, {
      complete: { value: true },
      naturalWidth: { value: 64 },
    });

    init(earlyDoc);

    expect(broken.getAttribute("src")).toBe("/plate.svg");
    expect(broken.hasAttribute("data-fallback")).toBe(false);
    expect(loaded.getAttribute("src")).toBe("loaded");
    expect(loaded.hasAttribute("data-fallback")).toBe(true);
    expect(pending.complete).toBe(false);
    expect(pending.getAttribute("src")).toBe("pending");
    expect(pending.hasAttribute("data-fallback")).toBe(true);
    early.window.close();
  });
  it("replaces broken images inserted after initialization", () => {
    const panel = doc.getElementById("week-panel");
    panel.innerHTML = '<img src="broken" data-fallback="/plate.svg">';
    const photo = panel.querySelector("img");
    photo.dispatchEvent(new win.Event("error"));
    expect(photo.getAttribute("src")).toBe("/plate.svg");
    expect(photo.hasAttribute("data-fallback")).toBe(false);
  });
});
