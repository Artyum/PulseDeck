(function () {
  const FIELD_LABELS = {
    user_id: "użytkownika",
    content: "treści wiadomości",
    title: "tytułu",
    description: "opisu",
    email: "adresu e-mail",
    password: "hasła",
    tag: "tagu",
  };

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
      if (field === "user_id") return "Wybierz użytkownika.";
      const label = FIELD_LABELS[field] || "wymaganego pola";
      return "Brakuje " + label + ".";
    }
    if (err.msg) return String(err.msg);
    return "Nieprawidłowe dane formularza.";
  }

  window.parseApiError = function (status, body) {
    try {
      const data = JSON.parse(body);
      const msg = messageFromDetail(data.detail);
      if (msg) return msg;
    } catch (e) {}
    if (status === 403) return "Brak uprawnień.";
    if (status === 404) return "Nie znaleziono.";
    if (status === 422) return "Nieprawidłowe dane formularza.";
    if (status === 429) return "Zbyt wiele prób. Spróbuj za chwilę.";
    if (status >= 500) return "Błąd serwera. Spróbuj ponownie.";
    return "Wystąpił błąd. Spróbuj ponownie.";
  };

  window.showConfirm = function (opts) {
    opts = opts || {};
    const dlg = document.getElementById("app-confirm");
    if (!dlg) return Promise.resolve(window.confirm(opts.message || "Kontynuować?"));
    const titleEl = document.getElementById("app-confirm-title");
    const msgEl = document.getElementById("app-confirm-message");
    const okBtn = document.getElementById("app-confirm-ok");
    titleEl.textContent = opts.title || "Potwierdzenie";
    msgEl.textContent = opts.message || "Czy na pewno chcesz kontynuować?";
    okBtn.textContent = opts.confirmLabel || "Potwierdź";
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
      title: form.getAttribute("data-confirm-title") || "Potwierdzenie",
      message: message,
      confirmLabel: form.getAttribute("data-confirm-action") || "Potwierdź",
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
        window.showToast("Nie udało się wysłać formularza.", "error");
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
    window.showToast("Nie udało się połączyć z serwerem.", "error");
  });

  document.addEventListener(
    "toggle",
    function (ev) {
      const menu = ev.target;
      if (!(menu instanceof HTMLDetailsElement) || !menu.classList.contains("issue-menu") || !menu.open) {
        return;
      }
      document.querySelectorAll("details.issue-menu[open]").forEach(function (other) {
        if (other !== menu) other.open = false;
      });
    },
    true
  );

  document.addEventListener("click", function (ev) {
    if (ev.target.closest("details.issue-menu")) return;
    document.querySelectorAll("details.issue-menu[open]").forEach(function (menu) {
      menu.open = false;
    });
  });

  function currentPref(key, fallback) {
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
    var active = currentPref(key, fallback);
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
    if (!root) return;
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

  document.querySelectorAll("[data-ui-storage-key]").forEach(syncPrefPicker);
})();
