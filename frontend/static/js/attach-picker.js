(function () {
  const IMAGE_RE = /\.(jpe?g|png|webp|gif)$/i;
  const inited = new WeakSet();

  function initPicker(root) {
    if (!root || inited.has(root)) return;
    const input = root.querySelector("[data-attach-input]");
    const preview = root.querySelector("[data-attach-preview]");
    const removeBox = root.querySelector("[data-attach-remove-box]");
    const btn = root.querySelector(".file-pick-btn");
    if (!input || !preview) return;
    inited.add(root);

    const TOTAL_MAX = Math.max(1, Number(root.getAttribute("data-attach-max")) || 3);
    let files = [];
    const urls = [];

    function existingVisible() {
      return preview.querySelectorAll("[data-existing-id]:not([hidden])").length;
    }

    function newSlots() {
      return Math.max(0, TOTAL_MAX - existingVisible());
    }

    function revokeUrls() {
      while (urls.length) URL.revokeObjectURL(urls.pop());
    }

    function syncCapacity() {
      const maxNew = newSlots();
      if (files.length > maxNew) files = files.slice(0, maxNew);
      if (btn) btn.classList.toggle("is-disabled", files.length >= maxNew);
    }

    function syncInput() {
      syncCapacity();
      const dt = new DataTransfer();
      files.forEach(function (f) {
        dt.items.add(f);
      });
      input.files = dt.files;
      render();
    }

    function render() {
      revokeUrls();
      preview.querySelectorAll("[data-new-file]").forEach(function (el) {
        el.remove();
      });
      files.forEach(function (file, idx) {
        const item = document.createElement("div");
        item.className = "attach-preview-item";
        item.setAttribute("data-new-file", "");

        if (IMAGE_RE.test(file.name)) {
          const img = document.createElement("img");
          const url = URL.createObjectURL(file);
          urls.push(url);
          img.src = url;
          img.alt = file.name;
          img.width = 80;
          img.height = 80;
          item.appendChild(img);
        } else {
          const label = document.createElement("span");
          label.className = "attach-preview-file";
          label.textContent = file.name;
          item.appendChild(label);
        }

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "attach-preview-remove";
        remove.setAttribute("aria-label", "Usuń " + file.name);
        remove.textContent = "×";
        remove.addEventListener("click", function () {
          files.splice(idx, 1);
          syncInput();
        });
        item.appendChild(remove);
        preview.appendChild(item);
      });
      preview.hidden = existingVisible() + files.length === 0;
    }

    function reset() {
      files = [];
      preview.querySelectorAll("[data-existing-id]").forEach(function (el) {
        el.hidden = false;
      });
      if (removeBox) removeBox.innerHTML = "";
      syncInput();
      input.value = "";
    }

    preview.querySelectorAll("[data-remove-existing]").forEach(function (btnEl) {
      btnEl.addEventListener("click", function () {
        const item = btnEl.closest("[data-existing-id]");
        if (!item) return;
        item.hidden = true;
        if (removeBox) {
          const inp = document.createElement("input");
          inp.type = "hidden";
          inp.name = "remove_attachment_ids";
          inp.value = item.getAttribute("data-existing-id") || "";
          removeBox.appendChild(inp);
        }
        syncInput();
      });
    });

    input.addEventListener("change", function () {
      const maxNew = newSlots();
      Array.from(input.files || []).forEach(function (file) {
        if (files.length >= maxNew) return;
        files.push(file);
      });
      files = files.slice(0, maxNew);
      syncInput();
    });

    const dlg = root.closest("dialog");
    if (dlg) {
      dlg.addEventListener("close", reset);
    }

    const form = root.closest("form");
    if (form && form.hasAttribute("hx-post")) {
      form.addEventListener("htmx:afterRequest", function (ev) {
        if (ev.detail && ev.detail.successful) reset();
      });
    }

    syncInput();
    root._attachReset = reset;
  }

  function scan(scope) {
    (scope || document).querySelectorAll("[data-attach-picker]").forEach(initPicker);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      scan(document);
    });
  } else {
    scan(document);
  }

  document.body.addEventListener("htmx:afterSwap", function (ev) {
    scan(ev.detail && ev.detail.target ? ev.detail.target : document);
  });
})();
