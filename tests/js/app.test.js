import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { JSDOM } from "jsdom";
import { init } from "../../schoolmenu/static/menus/app.js";

describe("menu progressive enhancement", () => {
  let doc, win, form, like, dislike, dialog;
  function fire(name, detail) {
    doc.dispatchEvent(new win.CustomEvent(name, { detail }));
  }
  beforeEach(() => {
    vi.useFakeTimers();
    win = new JSDOM(
      `<body><div id="save-status"></div><dialog id="food-dialog"><button data-close-dialog>Close</button><div id="dialog-content"></div></dialog><div id="week-panel"><label><input id="compact-disliked" type="checkbox" checked>Compact disliked items</label><a data-food-detail href="/food">Food</a><form class="preference-form" data-saved-state="neutral"><input type="hidden" name="state" value="neutral"><input type="checkbox" id="like" value="liked"><input type="checkbox" id="dislike" value="disliked"><button name="state" value="liked">Like</button><button name="state" value="neutral">Clear</button></form></div><input id="other" type="date"><img id="photo" src="broken" data-fallback="/plate.svg"></body>`,
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
    init(doc);
  });
  afterEach(() => {
    vi.useRealTimers();
    win.close();
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
});
