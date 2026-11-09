/** Progressive enhancement. All saved state and lunch decisions stay on the server. */
export function init(doc) {
  doc.body.classList.add("js-enabled");
  const dialog = doc.getElementById("food-dialog");
  const status = doc.getElementById("save-status");
  let opener;
  let focusId;
  let statusTimer;
  function announce(text) {
    clearTimeout(statusTimer);
    status.textContent = text;
    if (text === "Saved.")
      statusTimer = setTimeout(() => {
        status.textContent = "";
      }, 2500);
  }
  function restore(form) {
    for (const input of form.querySelectorAll('[type="checkbox"]')) {
      input.checked = input.value === form.dataset.savedState;
    }
  }
  doc.addEventListener("change", (event) => {
    const input = event.target;
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
      if (event.detail.successful) announce("Saved.");
      else {
        restore(form);
        announce(
          "Could not save. Your previous preference is unchanged. Please retry.",
        );
      }
    } else if (!event.detail.successful)
      announce("Could not load food details. Please retry.");
  });
  doc.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target.id === "dialog-content") dialog.showModal();
    if (event.detail.target.id === "week-panel" && focusId)
      doc.getElementById(focusId)?.focus();
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
