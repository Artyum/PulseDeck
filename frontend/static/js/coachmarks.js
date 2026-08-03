(function () {
  var STORAGE_PREFIX = "pulsedeck_coachmarks_seen:";
  var GAP = 18;
  var active = Object.create(null);
  var scanQueued = false;

  function i18n(key, fallback) {
    var value = (window.__i18n || {})[key];
    return value != null && value !== "" ? value : fallback || key;
  }

  function storageKey() {
    var id = document.body && document.body.getAttribute("data-user-id");
    return id ? STORAGE_PREFIX + id : "";
  }

  function readSeen() {
    var key = storageKey();
    if (!key) return {};
    try {
      var parsed = JSON.parse(localStorage.getItem(key) || "{}");
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  function markSeen(id) {
    var key = storageKey();
    if (!key) return;
    var map = readSeen();
    if (map[id]) return;
    map[id] = true;
    try {
      localStorage.setItem(key, JSON.stringify(map));
    } catch (e) {}
  }

  function isVisible(el) {
    if (!el || !(el instanceof Element)) return false;
    if (el.closest("[hidden]")) return false;
    var dialog = el.closest("dialog");
    if (dialog && !dialog.open) return false;
    return el.getClientRects().length > 0;
  }

  function findAnchor(id) {
    var nodes = document.querySelectorAll('[data-coachmark="' + id + '"]');
    var fallback = null;
    for (var i = 0; i < nodes.length; i++) {
      if (!isVisible(nodes[i])) continue;
      if (nodes[i].closest("dialog[open]")) return nodes[i];
      if (!fallback) fallback = nodes[i];
    }
    return fallback;
  }

  function place(el, anchor) {
    var rect = anchor.getBoundingClientRect();
    var tip = el.getBoundingClientRect();
    var vw = window.innerWidth || 0;
    var vh = window.innerHeight || 0;
    var mid = rect.left + rect.width / 2;
    var left = mid - tip.width / 2;
    var top = rect.bottom + GAP;
    var side = "below";

    if (top + tip.height > vh - 8 && rect.top - tip.height - GAP >= 8) {
      top = rect.top - tip.height - GAP;
      side = "above";
    }
    left = Math.min(Math.max(8, left), Math.max(8, vw - tip.width - 8));
    top = Math.max(8, top);

    el.classList.toggle("coachmark--below", side === "below");
    el.classList.toggle("coachmark--above", side === "above");
    el.style.left = Math.round(left) + "px";
    el.style.top = Math.round(top) + "px";
    return Math.round(left) + "," + Math.round(top) + "," + side + "," + Math.round(rect.top) + "," + Math.round(rect.left) + "," + Math.round(tip.width) + "," + Math.round(tip.height);
  }

  function dismiss(id) {
    var entry = active[id];
    if (!entry || !entry.el) {
      delete active[id];
      return;
    }
    try {
      if (entry.el.matches && entry.el.matches(":popover-open")) entry.el.hidePopover();
    } catch (e) {}
    if (entry.el.parentNode) entry.el.parentNode.removeChild(entry.el);
    delete active[id];
  }

  function revealStable(id) {
    var entry = active[id];
    if (!entry || !entry.el || !entry.anchor) return;

    var el = entry.el;
    var prev = "";
    var stable = 0;
    var tries = 0;

    function finish() {
      place(el, entry.anchor);
      el.style.visibility = "";
      el.classList.add("is-shown");
      entry.ready = true;
      markSeen(id);
    }

    function tick() {
      if (!active[id] || active[id].el !== el) return;
      if (!document.contains(entry.anchor) || !isVisible(entry.anchor)) {
        dismiss(id);
        return;
      }
      var key = place(el, entry.anchor);
      tries += 1;
      if (key === prev) stable += 1;
      else {
        prev = key;
        stable = 0;
      }
      if (stable < 2 && tries < 24) {
        requestAnimationFrame(tick);
        return;
      }
      finish();
    }

    function start() {
      if (!active[id] || active[id].el !== el) return;
      el.style.visibility = "hidden";
      try {
        if (typeof el.showPopover === "function") {
          el.setAttribute("popover", "manual");
          el.showPopover();
        }
      } catch (e) {}
      requestAnimationFrame(tick);
    }

    if (entry.anchor.closest("dialog")) window.setTimeout(start, 100);
    else start();
  }

  function render(hint, anchor) {
    var body = i18n("coachmarks." + hint.id + ".body", "");
    if (!body || active[hint.id]) return;

    var el = document.createElement("div");
    el.className = "coachmark coachmark--below";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");

    var text = document.createElement("p");
    text.className = "coachmark-body";
    text.textContent = body;
    el.appendChild(text);

    if (hint.href) {
      var link = document.createElement("a");
      link.className = "coachmark-cta";
      link.href = hint.href;
      link.textContent = i18n("coachmarks." + hint.id + ".cta", hint.href);
      el.appendChild(link);
    }

    var close = document.createElement("button");
    close.type = "button";
    close.className = "coachmark-close";
    close.setAttribute("aria-label", i18n("coachmarks.dismiss", "Dismiss"));
    close.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      dismiss(hint.id);
    });
    el.appendChild(close);

    active[hint.id] = { el: el, anchor: anchor, ready: false };
    document.body.appendChild(el);
    revealStable(hint.id);
  }

  function syncActive() {
    Object.keys(active).forEach(function (id) {
      var entry = active[id];
      if (!entry || !entry.el || !entry.anchor || !document.contains(entry.anchor) || !isVisible(entry.anchor)) {
        dismiss(id);
        return;
      }
      if (entry.ready) place(entry.el, entry.anchor);
    });
  }

  function scan() {
    if (!storageKey()) return;
    var catalog = window.__coachmarkCatalog;
    if (!catalog || !catalog.length) return;

    syncActive();
    var seen = readSeen();

    for (var i = 0; i < catalog.length; i++) {
      var hint = catalog[i];
      if (!hint || !hint.id || seen[hint.id] || active[hint.id]) continue;
      if (hint.match && !hint.match()) continue;
      var anchor = findAnchor(hint.id);
      if (!anchor || (hint.when && !hint.when(anchor))) continue;
      render(hint, anchor);
    }
  }

  function scheduleScan(extraFrame) {
    if (scanQueued) return;
    scanQueued = true;
    requestAnimationFrame(function () {
      if (!extraFrame) {
        scanQueued = false;
        scan();
        return;
      }
      requestAnimationFrame(function () {
        scanQueued = false;
        scan();
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      scheduleScan();
    });
  } else {
    scheduleScan();
  }

  document.addEventListener("htmx:afterSettle", function () {
    scheduleScan(true);
  });
  document.addEventListener("htmx:pushedIntoHistory", function () {
    scheduleScan();
  });
  document.addEventListener(
    "toggle",
    function (ev) {
      if (!ev.target || ev.target.tagName !== "DIALOG") return;
      scheduleScan(!!ev.target.open);
      if (ev.target.open) {
        window.setTimeout(syncActive, 180);
      }
    },
    true
  );
  window.addEventListener("resize", syncActive, { passive: true });
  window.addEventListener("scroll", syncActive, { passive: true, capture: true });
})();
