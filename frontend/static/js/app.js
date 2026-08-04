(function () {
  function loadI18n() {
    var el = document.getElementById("app-i18n");
    if (!el) return {};
    try {
      var parsed = JSON.parse(el.textContent || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (e) {
      return {};
    }
  }
  window.__i18n = loadI18n();

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

  var TOAST_MAX = 2;
  var feedbackSeq = 0;
  var FIELD_WRAP_SEL = ".admin-form-field, .admin-field, [data-field-wrap]";

  function cssEscape(value) {
    var s = String(value);
    if (window.CSS && typeof CSS.escape === "function") return CSS.escape(s);
    return s.replace(/([\\"#.:[\]])/g, "\\$1");
  }

  function feedbackLevel(level) {
    if (level === "success" || level === "warning") return level;
    return "error";
  }

  function fieldFromLoc(loc) {
    if (!Array.isArray(loc)) return null;
    for (var i = loc.length - 1; i >= 0; i--) {
      if (loc[i] !== "body" && loc[i] !== "query" && loc[i] !== "path") return String(loc[i]);
    }
    return null;
  }

  function messageForValidationErr(err, field) {
    if (err && err.type === "missing") {
      if (field === "user_id") return i18n("validation.missing_user", "Select a user");
      return i18nFormat("validation.missing_field", "Missing {label}", { label: fieldLabel(field) });
    }
    if (err && err.msg) return String(err.msg);
    return i18n("errors.validation", "Invalid form data");
  }

  function statusFallbackMessage(status) {
    if (status === 403) return i18n("errors.forbidden", "No permission.");
    if (status === 404) return i18n("errors.not_found", "Not found.");
    if (status === 422) return i18n("errors.validation", "Invalid form data");
    if (status === 429) return i18n("errors.rate_limit", "Too many attempts. Try again shortly.");
    if (status >= 500) return i18n("errors.server", "Server error. Please try again.");
    return i18n("errors.generic", "Something went wrong. Please try again.");
  }

  function parseDetailItem(err) {
    if (!err) return null;
    if (typeof err === "string") return { field: null, message: err, level: "error" };
    if (err.field != null && err.message != null) {
      return { field: String(err.field), message: String(err.message), level: feedbackLevel(err.level) };
    }
    var field = fieldFromLoc(err.loc);
    return { field: field, message: messageForValidationErr(err, field), level: "error" };
  }

  function findFieldControl(root, field) {
    if (!field) return null;
    var scope = root && root.querySelector ? root : document;
    var key = cssEscape(field);
    return scope.querySelector('[name="' + key + '"]') || scope.querySelector("#" + key) || scope.querySelector('[data-field="' + key + '"]');
  }

  function parseFeedback(status, body, root) {
    var fieldErrors = [];
    var globalErrors = [];
    var scope = root && root.querySelector ? root : document;
    function pushItem(item) {
      if (!item || !item.message) return;
      var field = item.field ? String(item.field) : null;
      if (field && findFieldControl(scope, field)) {
        fieldErrors.push({ field: field, message: item.message, level: feedbackLevel(item.level) });
      } else {
        globalErrors.push({ message: item.message, level: feedbackLevel(item.level) });
      }
    }
    try {
      var data = typeof body === "string" ? JSON.parse(body) : body;
      var detail = data && data.detail;
      if (detail != null) {
        if (typeof detail === "string") pushItem({ field: null, message: detail, level: "error" });
        else if (Array.isArray(detail))
          detail.forEach(function (err) {
            pushItem(parseDetailItem(err));
          });
        else if (typeof detail === "object") pushItem(parseDetailItem(detail));
      }
    } catch (e) {}
    if (!fieldErrors.length && !globalErrors.length) {
      globalErrors.push({ message: statusFallbackMessage(status), level: "error" });
    }
    return { fieldErrors: fieldErrors, globalErrors: globalErrors };
  }

  function ensureToastStack() {
    var stack = document.getElementById("toast-stack");
    if (stack) return stack;
    stack = document.createElement("div");
    stack.id = "toast-stack";
    stack.className = "toast-stack";
    stack.setAttribute("aria-live", "polite");
    document.body.appendChild(stack);
    return stack;
  }

  function promoteToastStack(stack) {
    if (!stack || typeof stack.showPopover !== "function") return;
    try {
      stack.setAttribute("popover", "manual");
      if (stack.matches(":popover-open")) stack.hidePopover();
      stack.showPopover();
    } catch (e) {}
  }

  function feedbackDisplayText(message) {
    return (message || "").toString().trim().replace(/\.+$/, "");
  }

  function renderToast(message, type) {
    var text = feedbackDisplayText(message);
    if (!text) return;
    var level = type === "success" ? "success" : "error";
    var stack = ensureToastStack();
    promoteToastStack(stack);
    while (stack.children.length >= TOAST_MAX) stack.removeChild(stack.firstChild);
    var el = document.createElement("div");
    el.className = "toast toast-" + level;
    el.setAttribute("role", "status");
    stack.setAttribute("aria-live", level === "error" ? "assertive" : "polite");
    el.textContent = text;
    stack.appendChild(el);
    var hide = function () {
      el.classList.add("toast-out");
      setTimeout(function () {
        if (el.parentNode) el.remove();
      }, 200);
    };
    el.addEventListener("click", hide);
    setTimeout(hide, text.length > 100 ? 6500 : 4500);
  }

  window.showToast = renderToast;

  function existingFeedbackHost(control) {
    if (!control) return null;
    var wrap = control.closest(FIELD_WRAP_SEL);
    if (wrap) {
      for (var i = 0; i < wrap.children.length; i++) {
        if (wrap.children[i].classList && wrap.children[i].classList.contains("field-feedback")) {
          return wrap.children[i];
        }
      }
    }
    var existing = control.nextElementSibling;
    return existing && existing.classList && existing.classList.contains("field-feedback") ? existing : null;
  }

  function feedbackHostFor(control) {
    var host = existingFeedbackHost(control);
    if (host) return host;
    host = document.createElement("p");
    host.className = "field-feedback";
    host.hidden = true;
    var wrap = control.closest(FIELD_WRAP_SEL);
    if (wrap) wrap.appendChild(host);
    else control.insertAdjacentElement("afterend", host);
    return host;
  }

  function clientValidityMessage(el) {
    if (el.validity.valueMissing) {
      return i18nFormat("validation.missing_field", "Missing {label}", {
        label: fieldLabel(el.getAttribute("name") || el.id || "required"),
      });
    }
    if (el.validity.patternMismatch && el.title) return el.title;
    return el.validationMessage || i18n("errors.validation", "Invalid form data");
  }

  function collectProjectsFieldError(form) {
    var wrap = form && form.querySelector ? form.querySelector("[data-projects-field]") : null;
    if (!wrap || wrap.hidden) return null;
    var boxes = wrap.querySelectorAll("input[name=project_ids]:not(:disabled)");
    if (!boxes.length) return null;
    var ok = Array.prototype.some.call(boxes, function (el) {
      return el.checked;
    });
    if (ok) return null;
    var msg = wrap.getAttribute("data-required-msg") || i18nFormat("validation.missing_field", "Missing {label}", { label: fieldLabel("project_ids") });
    return { field: "project_ids", message: msg, level: "error" };
  }

  function collectClientFieldErrors(form) {
    var errors = [];
    if (!form || !form.elements) return errors;
    var projectsErr = collectProjectsFieldError(form);
    if (projectsErr) errors.push(projectsErr);
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!(el instanceof HTMLElement)) return;
      if (el.disabled || el.type === "hidden" || el.type === "submit" || el.type === "button") return;
      if (el.name === "project_ids") return;
      if (typeof el.checkValidity !== "function" || el.checkValidity()) return;
      var field = el.getAttribute("name") || el.id;
      if (!field) return;
      errors.push({ field: field, message: clientValidityMessage(el), level: "error" });
    });
    return errors;
  }

  function applyClientFormValidation(form) {
    var fieldErrors = collectClientFieldErrors(form);
    if (!fieldErrors.length) return true;
    applyFeedback({ root: form, fieldErrors: fieldErrors, globalErrors: [] });
    return false;
  }

  function armFormValidation(root) {
    (root || document).querySelectorAll("form").forEach(function (form) {
      form.setAttribute("novalidate", "");
    });
  }

  function autoResizeTextarea(el) {
    if (!(el instanceof HTMLTextAreaElement)) return;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }
  window.autoResizeTextarea = autoResizeTextarea;

  function armAutoResize(root) {
    (root || document).querySelectorAll("textarea[data-auto-resize]").forEach(autoResizeTextarea);
  }

  function armDomEnhancements(root) {
    armFormValidation(root);
    armAutoResize(root);
    armIssueStickyHeads(root);
    syncSidebarToggles(root);
  }

  function syncSidebarToggles(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var shells = scope.matches && scope.matches("[data-sidebar]") ? [scope] : Array.prototype.slice.call(scope.querySelectorAll("[data-sidebar]"));
    shells.forEach(function (shell) {
      var open = shell.classList.contains("is-sidebar-open");
      shell.querySelectorAll("[data-sidebar-toggle]").forEach(function (btn) {
        var label = open ? btn.getAttribute("data-label-hide") : btn.getAttribute("data-label-show");
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        if (label) {
          btn.setAttribute("aria-label", label);
          btn.setAttribute("title", label);
        }
      });
    });
  }

  document.body.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-sidebar-toggle], [data-sidebar-backdrop]");
    if (!btn) return;
    var shell = btn.closest("[data-sidebar]");
    if (!shell) return;
    shell.classList.toggle("is-sidebar-open");
    syncSidebarToggles(shell);
  });

  function appHeaderOffsetPx() {
    var header = document.querySelector(".app-header");
    return header ? header.getBoundingClientRect().height : 0;
  }

  function armIssueStickyHeads(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("[data-issue-sticky-head]").forEach(function (head) {
      if (head.dataset.stickyArmed === "1") return;
      head.dataset.stickyArmed = "1";
      var sentinel = head.previousElementSibling;
      if (!sentinel || !sentinel.hasAttribute("data-issue-sticky-sentinel")) return;

      var observer = null;
      function syncStickyOffset() {
        if (observer) observer.disconnect();
        var top = appHeaderOffsetPx();
        head.style.top = top ? top + "px" : "";
        observer = new IntersectionObserver(
          function (entries) {
            var entry = entries[0];
            if (!entry) return;
            head.classList.toggle("is-compact", !entry.isIntersecting);
          },
          { rootMargin: "-" + top + "px 0px 0px 0px", threshold: 0 }
        );
        observer.observe(sentinel);
      }

      syncStickyOffset();
      window.addEventListener("resize", syncStickyOffset, { passive: true });
    });
  }

  armDomEnhancements(document);
  document.body.addEventListener("htmx:afterSwap", function (ev) {
    armDomEnhancements(ev.detail && ev.detail.target ? ev.detail.target : document);
  });
  document.addEventListener("input", function (ev) {
    var el = ev.target;
    if (!(el instanceof HTMLTextAreaElement) || !el.hasAttribute("data-auto-resize")) return;
    autoResizeTextarea(el);
  });

  function clearFieldFeedback(control) {
    if (!control) return;
    control.removeAttribute("aria-invalid");
    var host = existingFeedbackHost(control);
    if (!host) return;
    var describedby = control.getAttribute("aria-describedby") || "";
    if (host.id && describedby) {
      var ids = describedby.split(/\s+/).filter(function (id) {
        return id && id !== host.id;
      });
      if (ids.length) control.setAttribute("aria-describedby", ids.join(" "));
      else control.removeAttribute("aria-describedby");
    }
    host.textContent = "";
    host.className = "field-feedback";
    host.hidden = true;
    host.removeAttribute("role");
  }

  function clearRootFieldFeedback(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll('[aria-invalid="true"]').forEach(clearFieldFeedback);
  }

  function showFieldFeedbackOn(control, message, level) {
    var text = feedbackDisplayText(message);
    if (!control || !text) return;
    var host = feedbackHostFor(control);
    feedbackSeq += 1;
    if (!host.id) host.id = "field-feedback-" + feedbackSeq;
    host.hidden = false;
    host.className = "field-feedback" + (level === "warning" ? " field-feedback-warning" : "");
    host.setAttribute("role", "alert");
    host.textContent = text;
    control.setAttribute("aria-invalid", "true");
    var ids = (control.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
    if (ids.indexOf(host.id) === -1) ids.push(host.id);
    control.setAttribute("aria-describedby", ids.join(" "));
    if (!control._pdFieldClearBound) {
      control._pdFieldClearBound = true;
      var clear = function () {
        clearFieldFeedback(control);
      };
      control.addEventListener("input", clear);
      control.addEventListener("change", clear);
    }
  }

  function applyFeedback(detail) {
    detail = detail || {};
    var root = detail.root || document;
    var fieldErrors = detail.fieldErrors || [];
    var globalErrors = (detail.globalErrors || []).slice();
    if (fieldErrors.length) clearRootFieldFeedback(root);
    var firstControl = null;
    fieldErrors.forEach(function (item) {
      if (!item) return;
      var control = findFieldControl(root, item.field);
      if (!control) {
        globalErrors.push({ message: item.message, level: item.level || "error" });
        return;
      }
      showFieldFeedbackOn(control, item.message, item.level || "error");
      if (!firstControl) firstControl = control;
    });
    if (firstControl) {
      try {
        firstControl.scrollIntoView({ behavior: "smooth", block: "center" });
      } catch (e) {}
      try {
        firstControl.focus({ preventScroll: true });
      } catch (e2) {
        try {
          firstControl.focus();
        } catch (e3) {}
      }
    }
    globalErrors.forEach(function (item) {
      if (item && item.message) renderToast(item.message, item.level);
    });
  }

  window.showFieldError = function (formOrRoot, field, message, level) {
    applyFeedback({
      root: formOrRoot || document,
      fieldErrors: [{ field: field, message: message, level: level || "error" }],
      globalErrors: [],
    });
  };

  function publishHttpFeedback(status, body, root) {
    var parsed = parseFeedback(status, body, root);
    applyFeedback({
      root: root || document,
      fieldErrors: parsed.fieldErrors,
      globalErrors: parsed.globalErrors,
    });
  }

  function readFlashItems(el) {
    if (!el) return [];
    try {
      return JSON.parse(el.textContent || "[]") || [];
    } catch (e) {
      return [];
    }
  }

  function applyFlashItems(items) {
    if (!Array.isArray(items) || !items.length) return;
    var fieldErrors = [];
    var globalErrors = [];
    items.forEach(function (item) {
      if (!item) return;
      var message = item.message != null ? String(item.message) : "";
      if (!message) return;
      var level = feedbackLevel(item.type || item.level || "error");
      if (item.field) fieldErrors.push({ field: String(item.field), message: message, level: level });
      else globalErrors.push({ message: message, level: level });
    });
    if (fieldErrors.length || globalErrors.length) {
      applyFeedback({ fieldErrors: fieldErrors, globalErrors: globalErrors });
    }
  }

  function softApplyHtml(body, nextUrl) {
    var doc;
    try {
      doc = new DOMParser().parseFromString(body, "text/html");
    } catch (e) {
      return false;
    }
    if (!doc || !doc.body) return false;
    var swapped = false;
    var mainIncoming = doc.querySelector(".admin-main");
    var mainCurrent = document.querySelector(".admin-main");
    if (mainIncoming && mainCurrent) {
      mainCurrent.replaceWith(document.importNode(mainIncoming, true));
      swapped = true;
    } else {
      [".profile-content", ".admin-narrow", ".admin-prefs", ".admin-page-head"].forEach(function (sel) {
        var incoming = doc.querySelector(sel);
        var current = document.querySelector(sel);
        if (incoming && current) {
          current.replaceWith(document.importNode(incoming, true));
          swapped = true;
        }
      });
    }
    if (swapped) armDomEnhancements(document);
    var items = readFlashItems(doc.getElementById("app-flash"));
    applyFlashItems(items);
    var liveFlash = document.getElementById("app-flash");
    if (liveFlash) liveFlash.remove();
    if (nextUrl) {
      try {
        var u = new URL(nextUrl, window.location.origin);
        history.replaceState(null, "", u.pathname);
      } catch (e3) {}
    }
    return swapped || items.length > 0;
  }

  function consumeAppFlash() {
    var el = document.getElementById("app-flash");
    if (!el) return;
    applyFlashItems(readFlashItems(el));
    el.remove();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", consumeAppFlash);
  else consumeAppFlash();

  window.showConfirm = function (opts) {
    opts = opts || {};
    const dlg = document.getElementById("app-confirm");
    if (!dlg) {
      return Promise.resolve(window.confirm(opts.message || i18n("confirm.continue", "Continue?")));
    }
    const titleEl = document.getElementById("app-confirm-title");
    const msgEl = document.getElementById("app-confirm-message");
    const okBtn = document.getElementById("app-confirm-ok");
    const cancelBtn = document.getElementById("app-confirm-cancel");
    titleEl.textContent = opts.title || i18n("confirm.title", "Confirmation");
    msgEl.textContent = opts.message || i18n("confirm.message_default", "Are you sure you want to continue?");
    okBtn.textContent = opts.confirmLabel || i18n("confirm.confirm_label", "Confirm");
    okBtn.className = opts.danger ? "btn btn-danger" : "btn btn-primary";
    if (cancelBtn) {
      cancelBtn.textContent = opts.cancelLabel || cancelBtn.getAttribute("data-default-label") || "Cancel";
    }
    return new Promise(function (resolve) {
      let settled = false;
      function finish(result) {
        if (settled) return;
        settled = true;
        okBtn.removeEventListener("click", onOk);
        dlg.removeEventListener("close", onClose);
        if (dlg.open) dlg.close();
        resolve(result);
      }
      function onOk() {
        finish(true);
      }
      function onClose() {
        finish(false);
      }
      okBtn.addEventListener("click", onOk);
      dlg.addEventListener("close", onClose);
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
      confirmLabel: form.getAttribute("data-confirm-action") || i18n("confirm.confirm_label", "Confirm"),
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
    clearRootFieldFeedback(form);
    if (!applyClientFormValidation(form)) return;
    confirmForForm(form)
      .then(function (ok) {
        if (!ok) return;
        const action = form.getAttribute("action") || window.location.href;
        var body = new FormData(form);
        var submitter = ev.submitter;
        if (submitter && submitter.name && (submitter.type === "submit" || submitter.type === "image")) {
          body.append(submitter.name, submitter.value);
        }
        return fetch(action, {
          method: "POST",
          body: body,
          headers: { "X-CSRF-Token": token },
          credentials: "same-origin",
          redirect: "follow",
        }).then(function (r) {
          if (r.redirected) {
            return r.text().then(function (body) {
              var next;
              try {
                next = new URL(r.url, window.location.origin);
              } catch (e) {
                window.location.href = r.url;
                return;
              }
              if (next.pathname === window.location.pathname && softApplyHtml(body, next.href)) {
                return;
              }
              window.location.href = next.href;
            });
          }
          return r.text().then(function (body) {
            if (!r.ok) {
              publishHttpFeedback(r.status, body, form);
              return;
            }
            const ctype = (r.headers.get("content-type") || "").toLowerCase();
            if (ctype.includes("application/json")) {
              try {
                const data = JSON.parse(body);
                if (data.detail) {
                  publishHttpFeedback(r.status || 400, body, form);
                  return;
                }
                if (data.message) {
                  window.showToast(String(data.message), "success");
                  return;
                }
              } catch (e) {}
            }
            if (softApplyHtml(body, window.location.href)) return;
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

  document.addEventListener("htmx:confirm", function (ev) {
    var elt = ev.detail && ev.detail.elt;
    if (!elt || !elt.closest) return;
    var form = elt.closest("form");
    if (!form || !form.getAttribute("data-confirm")) return;
    ev.preventDefault();
    confirmForForm(form).then(function (ok) {
      if (ok) ev.detail.issueRequest(true);
    });
  });

  document.addEventListener("htmx:beforeSwap", function (ev) {
    if (ev.detail.xhr.status >= 400) {
      ev.detail.shouldSwap = false;
    }
  });

  document.addEventListener("htmx:beforeRequest", function (ev) {
    var src = ev.detail && ev.detail.elt;
    var form = src && src.closest ? src.closest("form") : null;
    if (!form) return;
    clearRootFieldFeedback(form);
    if (!applyClientFormValidation(form)) {
      ev.preventDefault();
    }
  });

  document.addEventListener("htmx:responseError", function (ev) {
    var src = ev.detail && ev.detail.elt;
    var root = src && src.closest ? src.closest("form") || src : document;
    publishHttpFeedback(ev.detail.xhr.status, ev.detail.xhr.responseText || "", root);
  });

  document.addEventListener("htmx:sendError", function () {
    window.showToast(i18n("errors.network", "Could not connect to the server."), "error");
  });

  function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function isAnimatedDialog(el) {
    return el instanceof HTMLDialogElement && (el.classList.contains("modal") || el.classList.contains("lightbox"));
  }

  var dialogFrames = [
    { opacity: 0, transform: "translateY(0.55rem) scale(0.97)" },
    { opacity: 1, transform: "translateY(0) scale(1)" },
  ];

  var lightboxFrames = [{ opacity: 0 }, { opacity: 1 }];

  function animateDialog(el, reverse, onDone) {
    if (!el.animate || prefersReducedMotion()) {
      if (onDone) onDone();
      return;
    }
    el.getAnimations().forEach(function (a) {
      a.cancel();
    });
    var lightbox = el.classList.contains("lightbox");
    var base = lightbox ? lightboxFrames : dialogFrames;
    var frames = reverse ? [base[1], base[0]] : base;
    var start = function () {
      var anim = el.animate(frames, {
        duration: reverse ? 220 : 320,
        easing: reverse ? "cubic-bezier(0.4, 0, 0.2, 1)" : "cubic-bezier(0.16, 1, 0.3, 1)",
        fill: "forwards",
      });
      var finish = function () {
        el.style.opacity = "";
        el.style.transform = "";
        try {
          anim.cancel();
        } catch (e) {}
        if (onDone) onDone();
      };
      anim.finished.then(finish).catch(finish);
    };
    if (!reverse) {
      el.style.opacity = "0";
      if (!lightbox) el.style.transform = dialogFrames[0].transform;
      requestAnimationFrame(start);
      return;
    }
    start();
  }

  var nativeShowModal = HTMLDialogElement.prototype.showModal;
  var nativeClose = HTMLDialogElement.prototype.close;

  HTMLDialogElement.prototype.showModal = function () {
    this.classList.remove("is-closing");
    nativeShowModal.call(this);
    if (isAnimatedDialog(this)) animateDialog(this, false);
  };

  HTMLDialogElement.prototype.close = function (returnValue) {
    if (!isAnimatedDialog(this) || !this.open) {
      nativeClose.call(this, returnValue);
      return;
    }
    if (this.classList.contains("is-closing")) return;
    var el = this;
    el.classList.add("is-closing");
    animateDialog(el, true, function () {
      el.classList.remove("is-closing");
      nativeClose.call(el, returnValue);
    });
  };

  document.addEventListener(
    "cancel",
    function (ev) {
      var dlg = ev.target;
      if (!(dlg instanceof HTMLDialogElement) || !dlg.open || dlg.id === "app-confirm") return;
      if (!isAnimatedDialog(dlg)) return;
      ev.preventDefault();
      requestCloseDialog(dlg);
    },
    true
  );

  document.addEventListener("click", function (ev) {
    var dismiss = ev.target.closest("[data-modal-dismiss]");
    if (dismiss) {
      requestCloseDialog(document.getElementById(dismiss.getAttribute("data-modal-dismiss")));
      return;
    }
    if (isAnimatedDialog(ev.target) && ev.target.open && !ev.target.hasAttribute("data-confirm-close")) {
      ev.target.close();
    }
  });

  function formIsDirty(form) {
    if (!(form instanceof HTMLFormElement)) return false;
    for (var i = 0; i < form.elements.length; i++) {
      var el = form.elements[i];
      if (!el.name || el.disabled) continue;
      var type = (el.type || "").toLowerCase();
      if (type === "button" || type === "submit" || type === "reset") continue;
      if (type === "file") {
        if (el.files && el.files.length) return true;
      } else if (type === "checkbox" || type === "radio") {
        if (el.checked !== el.defaultChecked) return true;
      } else if (String(el.value || "") !== String(el.defaultValue || "")) {
        return true;
      }
    }
    return false;
  }

  function requestCloseDialog(dlg) {
    if (!(dlg instanceof HTMLDialogElement) || !dlg.open) return;
    var confirmDlg = document.getElementById("app-confirm");
    if (confirmDlg && confirmDlg.open) return;
    if (dlg.hasAttribute("data-confirm-close") && formIsDirty(dlg.querySelector("form"))) {
      window
        .showConfirm({
          title: i18n("confirm.discard_ticket.title", "Discard ticket?"),
          message: i18n("confirm.discard_ticket.message", "The form has filled-in data. Cancel and discard changes?"),
          confirmLabel: i18n("confirm.discard_ticket.action", "Cancel creation"),
          cancelLabel: i18n("confirm.discard_ticket.cancel", "Back to editing"),
          danger: true,
        })
        .then(function (ok) {
          if (ok) dlg.close();
        });
      return;
    }
    dlg.close();
  }

  function resolveFormSelect(el) {
    return el.closest("[data-form-select]");
  }

  function setFormSelectValue(root, value) {
    var input = root.querySelector("[data-form-select-input]");
    var face = root.querySelector("[data-form-select-face]");
    var opt = root.querySelector('[data-form-select-option][data-value="' + value + '"]');
    var label = opt ? opt.getAttribute("data-label") || (opt.textContent || "").trim() : "";
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
  }

  document.addEventListener("input", function (ev) {
    if (!ev.target || ev.target.id !== "feed-q") return;
    var field = ev.target.closest(".feed-search-field");
    var clear = field && field.querySelector("[data-feed-search-clear]");
    if (clear) clear.hidden = !ev.target.value;
  });

  document.addEventListener("click", function (ev) {
    var searchClear = ev.target.closest("[data-feed-search-clear]");
    if (searchClear) {
      ev.preventDefault();
      var searchField = searchClear.closest(".feed-search-field");
      var searchInput = searchField && searchField.querySelector("input[name='q']");
      var searchForm = searchClear.closest("form");
      if (!searchInput || !searchForm) return;
      searchInput.value = "";
      searchClear.hidden = true;
      searchForm.requestSubmit();
      return;
    }
    var clearBtn = ev.target.closest("[data-feed-filter-clear]");
    if (clearBtn) {
      ev.preventDefault();
      var clearUrl = clearBtn.getAttribute("data-feed-filter-clear-url");
      if (clearUrl) {
        window.location.assign(clearUrl);
        return;
      }
      var clearForm = clearBtn.closest("form");
      if (!clearForm) return;
      clearForm.querySelectorAll("input[name='q'], input[name='tag']").forEach(function (el) {
        el.value = "";
      });
      clearForm.querySelectorAll("[data-form-select]").forEach(function (root) {
        var input = root.querySelector("[data-form-select-input]");
        var name = input ? input.getAttribute("name") : "";
        setFormSelectValue(root, name === "sort" ? "created_at" : "");
      });
      clearForm.querySelectorAll('input[type="checkbox"]').forEach(function (el) {
        el.checked = false;
      });
      var formId = clearForm.getAttribute("id");
      if (formId) {
        document.querySelectorAll('input[type="checkbox"][form="' + formId + '"]').forEach(function (el) {
          el.checked = false;
        });
      }
      clearForm.querySelectorAll('input[type="hidden"][name="view"]').forEach(function (el) {
        el.remove();
      });
      clearForm.requestSubmit();
      return;
    }
    var btn = ev.target.closest("[data-form-select-option]");
    if (!btn) return;
    var root = resolveFormSelect(btn);
    if (!root || root.hasAttribute("data-disabled")) return;
    ev.preventDefault();
    var value = btn.getAttribute("data-value") || "";
    setFormSelectValue(root, value);
    var alpineRoot = root.closest("[x-data]");
    if (alpineRoot && typeof Alpine !== "undefined") {
      Alpine.$data(alpineRoot).open = false;
    }
    if (root.hasAttribute("data-submit-on-pick")) {
      var input = root.querySelector("[data-form-select-input]");
      var form = root.closest("form");
      if (!form && input) {
        var formId = input.getAttribute("form");
        if (formId) form = document.getElementById(formId);
      }
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
    document.cookie = encodeURIComponent(name) + "=" + encodeURIComponent(value) + "; Path=/; Max-Age=" + maxAge + "; SameSite=Lax";
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

  function readGradientMap(key) {
    if (!key) return {};
    try {
      var parsed = JSON.parse(localStorage.getItem(key) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  function writeGradientMap(key, map) {
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify(map));
    } catch (e) {}
  }

  function isGradientOn(map, themeId) {
    return map[themeId] !== false && map[themeId] !== "off";
  }

  function applyThemeGradient(themeId, gradientKey) {
    document.documentElement.setAttribute("data-theme-gradient", isGradientOn(readGradientMap(gradientKey), themeId) ? "on" : "off");
  }

  function applyThemeScheme(themeId, root) {
    var darkAttr = (root && root.getAttribute("data-ui-dark-themes")) || "";
    var darkThemes = darkAttr ? darkAttr.split(",") : [];
    document.documentElement.setAttribute("data-scheme", darkThemes.indexOf(themeId) !== -1 ? "dark" : "light");
  }

  function syncPrefPicker(root) {
    if (!root) return;
    var key = root.getAttribute("data-ui-storage-key");
    var fallback = root.getAttribute("data-ui-fallback") || "";
    if (!key) return;
    var active = currentPref(root, key, fallback);
    var gradientKey = root.getAttribute("data-ui-gradient-key");
    var gradientMap = readGradientMap(gradientKey);
    root.querySelectorAll("[data-ui-value]").forEach(function (btn) {
      var on = btn.getAttribute("data-ui-value") === active;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.setAttribute("aria-checked", on ? "true" : "false");
    });
    if (!gradientKey) return;
    root.querySelectorAll("[data-theme-gradient-for]").forEach(function (input) {
      input.checked = isGradientOn(gradientMap, input.getAttribute("data-theme-gradient-for"));
    });
    applyThemeGradient(active, gradientKey);
  }

  document.addEventListener("click", function (ev) {
    if (ev.target.closest(".theme-gradient-switch")) return;
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
    if (attr === "data-theme") applyThemeScheme(value, root);
    var gradientKey = root.getAttribute("data-ui-gradient-key");
    if (gradientKey) applyThemeGradient(value, gradientKey);
    syncPrefPicker(root);
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    var btn = ev.target.closest(".theme-option[data-ui-value]");
    if (!btn || ev.target.closest(".theme-gradient-switch")) return;
    ev.preventDefault();
    btn.click();
  });

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  function postForm(url, fields) {
    var body = new FormData();
    Object.keys(fields).forEach(function (k) {
      if (fields[k] != null && fields[k] !== "") body.append(k, fields[k]);
    });
    var token = csrfToken();
    return fetch(url, {
      method: "POST",
      body: body,
      headers: token ? { "X-CSRF-Token": token } : {},
      credentials: "same-origin",
      redirect: "follow",
    });
  }

  function detectDatetimeFormat(locale) {
    var lower = (locale || "").toLowerCase().replace("_", "-");
    var primary = lower.split("-")[0];
    if (lower.indexOf("en-us") === 0 || lower.indexOf("en-ph") === 0) return "US_SLASH";
    if (lower.indexOf("en-gb") === 0 || lower.indexOf("en-au") === 0 || lower.indexOf("en-nz") === 0 || lower.indexOf("en-ie") === 0) {
      return "UK_SLASH";
    }
    if (primary === "sv") return "ISO_8601";
    if ("pl de cs sk hu ro bg uk ru hr sl sr fr it es pt nl da fi no".split(" ").indexOf(primary) >= 0) {
      return "EU_DOT";
    }
    return "ISO_8601";
  }

  document.addEventListener("change", function (ev) {
    var el = ev.target;
    if (!(el instanceof HTMLElement)) return;
    if (el.hasAttribute("data-theme-gradient-for")) {
      var themeId = el.getAttribute("data-theme-gradient-for");
      var root = el.closest("[data-ui-gradient-key]");
      if (!root || !themeId) return;
      var gradientKey = root.getAttribute("data-ui-gradient-key");
      var map = readGradientMap(gradientKey);
      map[themeId] = el.checked;
      writeGradientMap(gradientKey, map);
      var themeKey = root.getAttribute("data-ui-storage-key");
      var themeAttr = root.getAttribute("data-ui-attr") || "data-theme";
      var fallback = root.getAttribute("data-ui-fallback") || "";
      if (currentPref(root, themeKey, fallback) !== themeId) {
        try {
          localStorage.setItem(themeKey, themeId);
        } catch (e) {}
        document.documentElement.setAttribute(themeAttr, themeId);
      }
      if (themeAttr === "data-theme") applyThemeScheme(themeId, root);
      applyThemeGradient(themeId, gradientKey);
      syncPrefPicker(root);
      return;
    }
    var prefsRoot = el.closest("[data-datetime-prefs]");
    if (prefsRoot && el.hasAttribute("data-datetime-pref") && (el instanceof HTMLSelectElement || el.hasAttribute("data-form-select-input"))) {
      var prefsUrl = prefsRoot.getAttribute("data-datetime-prefs-url");
      var formatInput = prefsRoot.querySelector('[data-datetime-pref="format"]');
      var tzInput = prefsRoot.querySelector('[data-datetime-pref="timezone"]');
      if (!prefsUrl || !formatInput || !tzInput) return;
      postForm(prefsUrl, {
        datetime_format: formatInput.value,
        timezone: tzInput.value,
      }).catch(function () {});
      return;
    }
    var notifRoot = el.closest("[data-notif-prefs]");
    if (notifRoot && el.hasAttribute("data-notif-pref")) {
      var notifUrl = notifRoot.getAttribute("data-notif-prefs-url");
      if (!notifUrl) return;
      var newTicket = notifRoot.querySelector('[data-notif-pref="new_ticket"]');
      var reply = notifRoot.querySelector('[data-notif-pref="reply"]');
      var update = notifRoot.querySelector('[data-notif-pref="update"]');
      postForm(notifUrl, {
        notify_new_ticket: newTicket && newTicket.checked ? "1" : "",
        notify_reply: reply && reply.checked ? "1" : "",
        notify_ticket_update: update && update.checked ? "1" : "",
      }).catch(function () {});
      return;
    }
    if (el.getAttribute("data-ui-cookie") !== "1") return;
    if (!(el instanceof HTMLSelectElement) && !el.hasAttribute("data-form-select-input")) return;
    var key = el.getAttribute("data-ui-storage-key");
    var value = el.value;
    if (!key || !value) return;
    writeCookie(key, value);
    postForm("/profile/language", { lang: value })
      .catch(function () {})
      .finally(function () {
        window.location.reload();
      });
  });

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-auth-show]");
    if (!btn) return;
    var card = btn.closest(".auth-card");
    if (!card) return;
    var target = btn.getAttribute("data-auth-show");
    if (!target) return;
    ev.preventDefault();
    card.querySelectorAll("[data-auth-panel]").forEach(function (panel) {
      var on = panel.getAttribute("data-auth-panel") === target;
      panel.hidden = !on;
      if (on) {
        var focusEl = panel.querySelector("input:not([type='hidden']), button[type='submit']");
        if (focusEl) focusEl.focus();
      }
    });
  });

  document.querySelectorAll("[data-ui-storage-key]").forEach(function (root) {
    if (root.matches("select") || root.hasAttribute("data-form-select-input")) return;
    syncPrefPicker(root);
  });

  (function probeDatetimePrefs() {
    var body = document.body;
    if (!body || body.getAttribute("data-datetime-prefs-locked") !== "0") return;
    var tz = "";
    try {
      tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (e) {}
    if (!tz) return;
    var navLang = (navigator.language || "").toString();
    var primary = navLang.toLowerCase().replace("_", "-").split("-")[0];
    var langKey = body.getAttribute("data-lang-storage-key") || "pulsedeck_lang";
    var availableLangs = (body.getAttribute("data-available-langs") || "").split(",").filter(Boolean);
    var detectedLang = !readCookie(langKey) && availableLangs.indexOf(primary) >= 0 ? primary : "";
    postForm("/profile/datetime-prefs-auto", {
      timezone: tz,
      datetime_format: detectDatetimeFormat(navLang),
      lang: detectedLang,
    })
      .then(function (r) {
        if (r.status === 200) window.location.reload();
      })
      .catch(function () {});
  })();
})();
