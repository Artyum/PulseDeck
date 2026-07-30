(function () {
  function i18n(key, fallback) {
    var dict = window.__i18n || {};
    var value = dict[key];
    return value != null && value !== "" ? value : fallback || key;
  }

  function i18nFormat(key, fallback, vars) {
    var text = i18n(key, fallback);
    if (!vars) return text;
    return text.replace(/\{(\w+)\}/g, function (_, name) {
      return vars[name] != null ? String(vars[name]) : "{" + name + "}";
    });
  }

  function fieldLabel(field) {
    return i18n("validation.field." + field, i18n("validation.field.required", "a required field"));
  }

  function ensureToastStack() {
    let stack = document.getElementById("toast-stack");
    if (stack) return stack;
    stack = document.createElement("div");
    stack.id = "toast-stack";
    stack.className = "toast-stack";
    stack.setAttribute("aria-live", "polite");
    document.body.appendChild(stack);
    return stack;
  }

  window.showToast = function (message, type) {
    const text = (message || "").toString().trim();
    if (!text) return;
    const stack = ensureToastStack();
    const el = document.createElement("div");
    el.className = "toast toast-" + (type === "success" ? "success" : "error");
    el.setAttribute("role", "status");
    el.textContent = text;
    stack.appendChild(el);
    const hide = function () {
      el.classList.add("toast-out");
      setTimeout(function () {
        el.remove();
      }, 200);
    };
    el.addEventListener("click", hide);
    setTimeout(hide, 4500);
  };

  function messageFromDetail(detail) {
    if (!detail) return null;
    if (typeof detail === "string") return detail;
    if (!Array.isArray(detail) || !detail.length) return null;
    const err = detail[0];
    const loc = err.loc || [];
    let field = null;
    for (let i = loc.length - 1; i >= 0; i--) {
      if (loc[i] !== "body" && loc[i] !== "query" && loc[i] !== "path") {
        field = String(loc[i]);
        break;
      }
    }
    if (err.type === "missing") {
      if (field === "user_id") return i18n("validation.missing_user", "Select a user.");
      return i18nFormat("validation.missing_field", "Missing {label}.", {
        label: fieldLabel(field),
      });
    }
    if (err.msg) return String(err.msg);
    return i18n("errors.validation", "Invalid form data.");
  }

  window.parseApiError = function (status, body) {
    try {
      const data = JSON.parse(body);
      const msg = messageFromDetail(data.detail);
      if (msg) return msg;
    } catch (e) {}
    if (status === 403) return i18n("errors.forbidden", "No permission.");
    if (status === 404) return i18n("errors.not_found", "Not found.");
    if (status === 422) return i18n("errors.validation", "Invalid form data.");
    if (status === 429) return i18n("errors.rate_limit", "Too many attempts. Try again shortly.");
    if (status >= 500) return i18n("errors.server", "Server error. Please try again.");
    return i18n("errors.generic", "Something went wrong. Please try again.");
  };

  window.showConfirm = function (opts) {
    opts = opts || {};
    const dlg = document.getElementById("app-confirm");
    if (!dlg) {
      return Promise.resolve(
        window.confirm(opts.message || i18n("confirm.continue", "Continue?"))
      );
    }
    const titleEl = document.getElementById("app-confirm-title");
    const msgEl = document.getElementById("app-confirm-message");
    const okBtn = document.getElementById("app-confirm-ok");
    titleEl.textContent = opts.title || i18n("confirm.title", "Confirmation");
    msgEl.textContent =
      opts.message || i18n("confirm.message_default", "Are you sure you want to continue?");
    okBtn.textContent = opts.confirmLabel || i18n("confirm.confirm_label", "Confirm");
    okBtn.className = opts.danger ? "btn btn-danger" : "btn btn-primary";
    return new Promise(function (resolve) {
      let settled = false;
      function finish(result) {
        if (settled) return;
        settled = true;
        okBtn.removeEventListener("click", onOk);
        dlg.querySelectorAll("[data-confirm-cancel]").forEach(function (btn) {
          btn.removeEventListener("click", onCancel);
        });
        dlg.removeEventListener("close", onClose);
        dlg.removeEventListener("click", onBackdrop);
        if (dlg.open) dlg.close();
        resolve(result);
      }
      function onOk() {
        finish(true);
      }
      function onCancel() {
        finish(false);
      }
      function onClose() {
        finish(false);
      }
      function onBackdrop(ev) {
        if (ev.target === dlg) finish(false);
      }
      okBtn.addEventListener("click", onOk);
      dlg.querySelectorAll("[data-confirm-cancel]").forEach(function (btn) {
        btn.addEventListener("click", onCancel);
      });
      dlg.addEventListener("close", onClose);
      dlg.addEventListener("click", onBackdrop);
      dlg.showModal();
      if (opts.danger) {
        const cancels = dlg.querySelectorAll("[data-confirm-cancel]");
        cancels[cancels.length - 1].focus();
      } else {
        okBtn.focus();
      }
    });
  };

  function confirmForForm(form) {
    const whenKey = form.getAttribute("data-confirm-when-key-changes");
    if (whenKey !== null) {
      const keyEl = form.elements.namedItem("project_key");
      const current = keyEl
        ? String(keyEl.value || "")
            .trim()
            .toUpperCase()
        : "";
      if (current === String(whenKey).trim().toUpperCase()) {
        return Promise.resolve(true);
      }
    }
    const message = form.getAttribute("data-confirm");
    if (!message) return Promise.resolve(true);
    return window.showConfirm({
      title: form.getAttribute("data-confirm-title") || i18n("confirm.title", "Confirmation"),
      message: message,
      confirmLabel:
        form.getAttribute("data-confirm-action") || i18n("confirm.confirm_label", "Confirm"),
      danger: form.hasAttribute("data-confirm-danger"),
    });
  }

  const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
  document.addEventListener("submit", function (ev) {
    const form = ev.target;
    if (!(form instanceof HTMLFormElement)) return;
    if ((form.getAttribute("method") || "get").toLowerCase() !== "post") return;
    if (form.hasAttribute("hx-post") || form.closest("[hx-boost]")) return;
    if (!token) return;
    if (ev.defaultPrevented) return;
    ev.preventDefault();
    confirmForForm(form)
      .then(function (ok) {
        if (!ok) return;
        const action = form.getAttribute("action") || window.location.href;
        return fetch(action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-CSRF-Token": token },
          credentials: "same-origin",
          redirect: "follow",
        }).then(function (r) {
          if (r.redirected) {
            window.location.href = r.url;
            return;
          }
          return r.text().then(function (body) {
            if (!r.ok) {
              window.showToast(window.parseApiError(r.status, body), "error");
              return;
            }
            const ctype = (r.headers.get("content-type") || "").toLowerCase();
            if (ctype.includes("application/json")) {
              try {
                const data = JSON.parse(body);
                if (data.detail) {
                  window.showToast(String(data.detail), "error");
                  return;
                }
              } catch (e) {}
            }
            document.open();
            document.write(body);
            document.close();
          });
        });
      })
      .catch(function () {
        window.showToast(i18n("errors.submit_failed", "Failed to submit the form."), "error");
      });
  });

  document.addEventListener("htmx:beforeSwap", function (ev) {
    if (ev.detail.xhr.status >= 400) {
      ev.detail.shouldSwap = false;
    }
  });

  document.addEventListener("htmx:responseError", function (ev) {
    window.showToast(window.parseApiError(ev.detail.xhr.status, ev.detail.xhr.responseText || ""), "error");
  });

  document.addEventListener("htmx:sendError", function () {
    window.showToast(i18n("errors.network", "Could not connect to the server."), "error");
  });

  function popIn(el, dy) {
    if (!el || !el.animate) return;
    var y = dy == null ? "-0.2rem" : dy;
    el.getAnimations().forEach(function (a) {
      a.cancel();
    });
    el.style.opacity = "0";
    el.style.transform = "translateY(" + y + ")";
    requestAnimationFrame(function () {
      var anim = el.animate(
        [
          { opacity: 0, transform: "translateY(" + y + ")" },
          { opacity: 1, transform: "translateY(0)" },
        ],
        { duration: 160, easing: "cubic-bezier(0.2, 0.85, 0.25, 1)", fill: "forwards" }
      );
      var clear = function () {
        el.style.opacity = "";
        el.style.transform = "";
        try {
          anim.cancel();
        } catch (e) {}
      };
      anim.finished.then(clear).catch(clear);
    });
  }

  var nativeShowModal = HTMLDialogElement.prototype.showModal;
  HTMLDialogElement.prototype.showModal = function () {
    nativeShowModal.call(this);
    if (this.classList.contains("modal")) popIn(this, "0.35rem");
    else if (this.classList.contains("lightbox")) popIn(this, "0");
  };

  function clearMenuPanel(panel) {
    if (!panel) return;
    panel._ownerMenu = null;
  }

  function placeMenuPanel(menu, panel) {
    panel._ownerMenu = menu;
  }

  function closeAllMenus(except) {
    document.querySelectorAll("details.issue-menu[open]").forEach(function (menu) {
      if (menu !== except) menu.open = false;
    });
  }

  function resolveFormSelect(el) {
    var root = el.closest("[data-form-select]");
    if (root) return root;
    var panel = el.closest(".issue-menu-panel");
    return (panel && panel._ownerMenu) || null;
  }

  document.addEventListener(
    "toggle",
    function (ev) {
      var menu = ev.target;
      if (!(menu instanceof HTMLDetailsElement) || !menu.classList.contains("issue-menu")) {
        return;
      }
      if (menu.hasAttribute("data-disabled")) {
        menu.open = false;
        return;
      }
      if (!menu.open) {
        menu.querySelectorAll(":scope > .issue-menu-panel").forEach(clearMenuPanel);
        return;
      }
      closeAllMenus(menu);
      menu.querySelectorAll(":scope > .issue-menu-panel").forEach(function (panel) {
        placeMenuPanel(menu, panel);
      });
    },
    true
  );

  document.addEventListener("click", function (ev) {
    if (ev.target.closest("details.issue-menu, .issue-menu-panel")) return;
    closeAllMenus();
  });

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-form-select-option]");
    if (!btn) return;
    var root = resolveFormSelect(btn);
    if (!root || root.hasAttribute("data-disabled")) return;
    ev.preventDefault();
    var input = root.querySelector("[data-form-select-input]");
    var face = root.querySelector("[data-form-select-face]");
    var value = btn.getAttribute("data-value") || "";
    var label = btn.getAttribute("data-label") || (btn.textContent || "").trim();
    if (input) {
      input.value = value;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (face) face.textContent = label;
    root.querySelectorAll("[data-form-select-option]").forEach(function (el) {
      var on = el.getAttribute("data-value") === value;
      el.classList.toggle("is-active", on);
      if (on) el.setAttribute("aria-current", "true");
      else el.removeAttribute("aria-current");
    });
    root.open = false;
    if (root.hasAttribute("data-submit-on-pick")) {
      var form = root.closest("form");
      if (form) form.requestSubmit();
    }
  });

  function readCookie(name) {
    var parts = ("; " + document.cookie).split("; " + name + "=");
    if (parts.length < 2) return null;
    return decodeURIComponent(parts.pop().split(";").shift() || "") || null;
  }

  function writeCookie(name, value) {
    var maxAge = 60 * 60 * 24 * 365 * 5;
    document.cookie =
      encodeURIComponent(name) +
      "=" +
      encodeURIComponent(value) +
      "; Path=/; Max-Age=" +
      maxAge +
      "; SameSite=Lax";
  }

  function currentPref(root, key, fallback) {
    if (root && root.getAttribute("data-ui-cookie") === "1") {
      return readCookie(key) || fallback;
    }
    try {
      return localStorage.getItem(key) || fallback;
    } catch (e) {
      return fallback;
    }
  }

  function syncPrefPicker(root) {
    if (!root) return;
    var key = root.getAttribute("data-ui-storage-key");
    var fallback = root.getAttribute("data-ui-fallback") || "";
    if (!key) return;
    var active = currentPref(root, key, fallback);
    root.querySelectorAll("[data-ui-value]").forEach(function (btn) {
      var on = btn.getAttribute("data-ui-value") === active;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-ui-value]");
    if (!btn) return;
    var root = btn.closest("[data-ui-storage-key]");
    if (!root || root.matches("select")) return;
    var key = root.getAttribute("data-ui-storage-key");
    var attr = root.getAttribute("data-ui-attr");
    var value = btn.getAttribute("data-ui-value");
    if (!key || !attr || !value) return;
    try {
      localStorage.setItem(key, value);
    } catch (e) {}
    document.documentElement.setAttribute(attr, value);
    syncPrefPicker(root);
  });

  document.addEventListener("change", function (ev) {
    var el = ev.target;
    if (!(el instanceof HTMLElement)) return;
    if (el.getAttribute("data-ui-cookie") !== "1") return;
    if (!(el instanceof HTMLSelectElement) && !el.hasAttribute("data-form-select-input")) return;
    var key = el.getAttribute("data-ui-storage-key");
    var value = el.value;
    if (!key || !value) return;
    writeCookie(key, value);
    window.location.reload();
  });

  document.querySelectorAll("[data-ui-storage-key]").forEach(function (root) {
    if (root.matches("select") || root.hasAttribute("data-form-select-input")) return;
    syncPrefPicker(root);
  });
})();
