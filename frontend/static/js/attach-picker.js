(function () {
  const IMAGE_RE = /\.(jpe?g|png|webp|gif)$/i;
  const ALLOWED_RE =
    /\.(jpe?g|png|webp|gif|pdf|docx|xlsx|pptx|txt|csv|log|json|xml|zip|rar|7z)$/i;
  const MIME_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "application/pdf": ".pdf",
  };
  const inited = new WeakSet();

  function normalizeFile(file) {
    if (!file) return null;
    if (file.name && ALLOWED_RE.test(file.name)) return file;
    const ext = MIME_EXT[(file.type || "").toLowerCase()];
    if (!ext) return null;
    return new File([file], "paste-" + Date.now() + ext, {
      type: file.type || "application/octet-stream",
      lastModified: Date.now(),
    });
  }

  function collectFiles(list) {
    const out = [];
    if (!list || !list.length) return out;
    for (var i = 0; i < list.length; i++) {
      var normalized = normalizeFile(list[i]);
      if (normalized) out.push(normalized);
    }
    return out;
  }

  function filesFromClipboard(cd) {
    if (!cd) return [];
    const raw = [];
    if (cd.items && cd.items.length) {
      for (var i = 0; i < cd.items.length; i++) {
        var item = cd.items[i];
        if (item.kind === "file") {
          var f = item.getAsFile();
          if (f) raw.push(f);
        }
      }
    } else if (cd.files && cd.files.length) {
      for (var j = 0; j < cd.files.length; j++) raw.push(cd.files[j]);
    }
    return collectFiles(raw);
  }

  function hasFileDrag(ev) {
    const types = ev.dataTransfer && ev.dataTransfer.types;
    if (!types) return false;
    return Array.prototype.indexOf.call(types, "Files") !== -1;
  }

  function initPicker(root) {
    if (!root || inited.has(root)) return;
    const input = root.querySelector("[data-attach-input]");
    const preview = root.querySelector("[data-attach-preview]");
    const removeBox = root.querySelector("[data-attach-remove-box]");
    const btn = root.querySelector(".file-pick-btn");
    const zone = root.querySelector(".file-pick-zone");
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
        var removeLabel = (window.__i18n && window.__i18n["attach.remove"]) || "Remove {name}";
        remove.setAttribute("aria-label", removeLabel.replace("{name}", file.name));
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

    function addFiles(picked) {
      if (!picked || !picked.length) return;
      const maxNew = newSlots();
      const room = Math.max(0, maxNew - files.length);
      if (picked.length > room) {
        var msg = (window.__i18n && window.__i18n["attach.too_many"]) || "You can attach up to {count} files.";
        if (typeof window.showToast === "function") {
          window.showToast(msg.replace("{count}", String(TOTAL_MAX)), "error");
        }
      }
      picked.forEach(function (file) {
        if (files.length >= maxNew) return;
        files.push(file);
      });
      files = files.slice(0, maxNew);
      syncInput();
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
      addFiles(collectFiles(input.files));
    });

    if (zone) {
      let dragDepth = 0;

      zone.addEventListener("dragenter", function (ev) {
        if (!hasFileDrag(ev)) return;
        ev.preventDefault();
        dragDepth += 1;
        zone.classList.add("is-dragover");
      });

      zone.addEventListener("dragover", function (ev) {
        if (!hasFileDrag(ev)) return;
        ev.preventDefault();
        if (ev.dataTransfer) ev.dataTransfer.dropEffect = "copy";
      });

      zone.addEventListener("dragleave", function () {
        dragDepth = Math.max(0, dragDepth - 1);
        if (!dragDepth) zone.classList.remove("is-dragover");
      });

      zone.addEventListener("drop", function (ev) {
        if (!hasFileDrag(ev)) return;
        ev.preventDefault();
        dragDepth = 0;
        zone.classList.remove("is-dragover");
        addFiles(collectFiles(ev.dataTransfer && ev.dataTransfer.files));
      });
    }

    const form = root.closest("form");
    if (form) {
      form.addEventListener("paste", function (ev) {
        const pasted = filesFromClipboard(ev.clipboardData);
        if (!pasted.length) return;
        ev.preventDefault();
        addFiles(pasted);
      });
      if (form.hasAttribute("hx-post")) {
        form.addEventListener("htmx:afterRequest", function (ev) {
          if (ev.detail && ev.detail.successful) reset();
        });
      }
    }

    const dlg = root.closest("dialog");
    if (dlg) {
      dlg.addEventListener("close", reset);
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
