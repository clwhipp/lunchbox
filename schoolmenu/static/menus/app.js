/** Progressive enhancement. All saved state and lunch decisions stay on the server. */
export function init(doc) {
  doc.body.classList.add("js-enabled");
  const dialog = doc.getElementById("food-dialog");
  const status = doc.getElementById("save-status");
  const compactPreferenceKey = "lunchbox.compactDisliked";
  let compactDisliked = true;
  try {
    compactDisliked =
      doc.defaultView.localStorage.getItem(compactPreferenceKey) !== "false";
  } catch {
    compactDisliked = true;
  }
  function syncCompactToggle() {
    const toggle = doc.getElementById("compact-disliked");
    if (toggle) toggle.checked = compactDisliked;
  }
  function setCompactDisliked(enabled) {
    compactDisliked = enabled;
    doc.body.classList.toggle("compact-disliked", enabled);
    syncCompactToggle();
    try {
      doc.defaultView.localStorage.setItem(
        compactPreferenceKey,
        String(enabled),
      );
    } catch {
      // Keep the in-page setting functional if browser storage is unavailable.
    }
  }
  doc.body.classList.toggle("compact-disliked", compactDisliked);
  syncCompactToggle();
  let opener;
  let focusId;
  let statusTimer;
  function announce(text, duration = 0) {
    clearTimeout(statusTimer);
    statusTimer = undefined;
    status.textContent = text;
    if (duration > 0)
      statusTimer = setTimeout(() => {
        status.textContent = "";
        statusTimer = undefined;
      }, duration);
  }
  function restore(form) {
    for (const input of form.querySelectorAll('[type="checkbox"]')) {
      input.checked = input.value === form.dataset.savedState;
    }
  }
  doc.addEventListener("change", (event) => {
    const input = event.target;
    if (input.matches("#compact-disliked")) {
      setCompactDisliked(input.checked);
      return;
    }
    const form = input.closest(".preference-form");
    if (!form || input.type !== "checkbox") return;
    const state = input.checked ? input.value : "neutral";
    for (const other of form.querySelectorAll('[type="checkbox"]')) {
      other.checked = other.value === state;
    }
    // Fallback submit buttons share the name; form.elements.state is then a collection.
    form.querySelector('input[name="state"]').value = state;
    focusId = input.id;
    form.requestSubmit();
  });
  doc.addEventListener("click", (event) => {
    const target = event.target.closest(
      "[data-food-detail], [data-close-dialog]",
    );
    if (!target) return;
    if (target.hasAttribute("data-close-dialog")) dialog.close();
    else opener = target;
  });
  dialog.addEventListener("close", () => {
    if (opener?.isConnected) opener.focus();
  });
  doc.addEventListener("htmx:beforeRequest", (event) => {
    if (event.detail.elt.matches(".preference-form")) {
      for (const input of doc.querySelectorAll(
        '.preference-form [type="checkbox"]',
      ))
        input.disabled = true;
      announce("Saving…");
    }
  });
  doc.addEventListener("htmx:afterRequest", (event) => {
    const form = event.detail.elt;
    if (form.matches(".preference-form")) {
      for (const input of doc.querySelectorAll(
        '.preference-form [type="checkbox"]',
      ))
        input.disabled = false;
      if (event.detail.successful) announce("Saved.", 2500);
      else {
        restore(form);
        announce(
          "Could not save. Your previous preference is unchanged. Please retry.",
          5000,
        );
      }
    } else if (!event.detail.successful)
      announce("Could not load food details. Please retry.", 5000);
  });
  doc.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target.id === "dialog-content") dialog.showModal();
    if (event.detail.target.id === "week-panel") {
      syncCompactToggle();
      if (focusId) doc.getElementById(focusId)?.focus();
    }
  });
  doc.addEventListener(
    "error",
    (event) => {
      const img = event.target;
      if (img.matches?.("img[data-fallback]")) {
        img.src = img.dataset.fallback;
        delete img.dataset.fallback;
      }
    },
    true,
  );
}
