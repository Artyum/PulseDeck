(function () {
  var STORAGE_PREFIX = "pulsedeck_coachmarks_seen:";
  var GAP = 18;
  var SPOT_PAD = 6;

  var tour = null;
  var scanQueued = false;
  var syncTimer = 0;
  var scrollWait = null;

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

  function writeSeen(map) {
    var key = storageKey();
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify(map));
    } catch (e) {}
  }

  function markSeen(id) {
    if (!id) return;
    var map = readSeen();
    if (map[id]) return;
    map[id] = true;
    writeSeen(map);
  }

  function markIdsSeen(ids) {
    if (!ids || !ids.length) return;
    var map = readSeen();
    var changed = false;
    for (var i = 0; i < ids.length; i++) {
      if (!ids[i] || map[ids[i]]) continue;
      map[ids[i]] = true;
      changed = true;
    }
    if (changed) writeSeen(map);
  }

  function prefersReducedMotion() {
    try {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) {
      return false;
    }
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
    var visible = null;
    var fallback = null;
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var dialog = node.closest("dialog");
      if (dialog && !dialog.open) continue;
      if (!fallback) fallback = node;
      if (!isVisible(node)) continue;
      if (node.closest("dialog[open]")) return node;
      if (!visible) visible = node;
    }
    return visible || fallback;
  }

  function hostFor(anchor) {
    return (anchor && anchor.closest("dialog[open]")) || document.body;
  }

  function catalog() {
    return window.__coachmarkCatalog || [];
  }

  function hintMatchesScope(hint, scope) {
    if (!hint || !hint.scope) return false;
    if (Array.isArray(hint.scope)) return hint.scope.indexOf(scope) >= 0;
    return hint.scope === scope;
  }

  function hintsForScope(scope) {
    if (!scope) return catalog();
    var list = [];
    var items = catalog();
    for (var i = 0; i < items.length; i++) {
      if (items[i] && hintMatchesScope(items[i], scope)) list.push(items[i]);
    }
    return list;
  }

  function collectSteps(scope, replay) {
    var seen = readSeen();
    var hints = hintsForScope(scope);
    var steps = [];
    for (var i = 0; i < hints.length; i++) {
      var hint = hints[i];
      if (!hint || !hint.id) continue;
      if (!replay && seen[hint.id]) continue;
      var anchor = findAnchor(hint.id);
      if (!anchor || (hint.when && !hint.when(anchor))) continue;
      var rect = anchor.getBoundingClientRect();
      steps.push({ hint: hint, anchor: anchor, top: rect.top, left: rect.left });
    }
    steps.sort(function (a, b) {
      if (a.top !== b.top) return a.top - b.top;
      return a.left - b.left;
    });
    return steps;
  }

  function ensureAnchorReachable(anchor) {
    if (!anchor || !anchor.closest) return;
    var mobileShell = anchor.closest(".nav-mobile-panel") && anchor.closest(".app-header-nav-mobile");
    if (mobileShell) {
      try {
        if (window.Alpine && typeof window.Alpine.$data === "function") {
          var mobileData = window.Alpine.$data(mobileShell);
          if (mobileData && !mobileData.open) mobileData.open = true;
        }
      } catch (e) {}
    }
    var panel = anchor.closest(".issue-sidebar, .admin-aside");
    if (!panel) return;
    var shell = panel.closest("[data-sidebar]");
    if (!shell || shell.classList.contains("is-sidebar-open")) return;
    try {
      if (window.getComputedStyle(panel).visibility !== "hidden") return;
    } catch (e) {
      return;
    }
    shell.classList.add("is-sidebar-open");
    shell.querySelectorAll("[data-sidebar-toggle]").forEach(function (btn) {
      var label = btn.getAttribute("data-label-hide");
      btn.setAttribute("aria-expanded", "true");
      if (label) {
        btn.setAttribute("aria-label", label);
        btn.setAttribute("title", label);
      }
    });
  }

  function place(el, anchor, host) {
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

    if (host !== document.body) {
      var hostRect = host.getBoundingClientRect();
      left -= hostRect.left;
      top -= hostRect.top;
    }

    el.classList.toggle("coachmark--below", side === "below");
    el.classList.toggle("coachmark--above", side === "above");
    el.style.left = Math.round(left) + "px";
    el.style.top = Math.round(top) + "px";
  }

  function placeSpotlight(spot, anchor, host) {
    if (!spot || !anchor) return;
    var rect = anchor.getBoundingClientRect();
    var left = rect.left - SPOT_PAD;
    var top = rect.top - SPOT_PAD;
    var width = rect.width + SPOT_PAD * 2;
    var height = rect.height + SPOT_PAD * 2;
    if (host !== document.body) {
      var hostRect = host.getBoundingClientRect();
      left -= hostRect.left;
      top -= hostRect.top;
    }
    spot.style.left = Math.round(left) + "px";
    spot.style.top = Math.round(top) + "px";
    spot.style.width = Math.max(0, Math.round(width)) + "px";
    spot.style.height = Math.max(0, Math.round(height)) + "px";
  }

  function focusables(root) {
    if (!root) return [];
    var nodes = root.querySelectorAll('button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])');
    var out = [];
    for (var i = 0; i < nodes.length; i++) {
      if (isVisible(nodes[i])) out.push(nodes[i]);
    }
    return out;
  }

  function destroyUi() {
    if (!tour) return;
    if (tour._onKey) {
      document.removeEventListener("keydown", tour._onKey, true);
      tour._onKey = null;
    }
    if (tour.el && tour.el.parentNode) tour.el.parentNode.removeChild(tour.el);
    if (tour.overlay && tour.overlay.parentNode) tour.overlay.parentNode.removeChild(tour.overlay);
    tour.el = null;
    tour.overlay = null;
    tour.spot = null;
    tour.host = null;
    tour.ready = false;
  }

  function endTour(markRemaining) {
    if (scrollWait) {
      clearTimeout(scrollWait);
      scrollWait = null;
    }
    if (!tour) return;
    if (markRemaining) {
      var ids = [];
      for (var i = tour.index; i < tour.steps.length; i++) {
        ids.push(tour.steps[i].hint.id);
      }
      markIdsSeen(ids);
    }
    destroyUi();
    tour = null;
  }

  function syncLayout() {
    if (!tour || !tour.ready || !tour.el || !tour.anchor) return;
    if (!document.contains(tour.anchor) || !isVisible(tour.anchor)) {
      skipMissingStep();
      return;
    }
    place(tour.el, tour.anchor, tour.host);
    placeSpotlight(tour.spot, tour.anchor, tour.host);
  }

  function scheduleSync() {
    if (syncTimer) cancelAnimationFrame(syncTimer);
    syncTimer = requestAnimationFrame(function () {
      syncTimer = 0;
      syncLayout();
    });
  }

  function skipMissingStep() {
    if (!tour) return;
    var next = tour.index + 1;
    if (next >= tour.steps.length) {
      endTour(false);
      scheduleScan();
      return;
    }
    showStep(next);
  }

  function go(delta) {
    if (!tour) return;
    var next = tour.index + delta;
    if (next < 0 || next >= tour.steps.length) return;
    showStep(next);
  }

  function skipTour() {
    if (!tour) return;
    endTour(true);
    scheduleScan();
  }

  function finishTour() {
    if (!tour) return;
    endTour(false);
    scheduleScan();
  }

  function buildCard(step, index, total) {
    var hint = step.hint;
    var el = document.createElement("div");
    el.className = "coachmark coachmark--below";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", i18n("coachmarks.tour_label", "Tips"));
    el.tabIndex = -1;

    var text = document.createElement("p");
    text.className = "coachmark-body";
    text.id = "coachmark-body-" + hint.id;
    text.textContent = i18n("coachmarks." + hint.id + ".body", "");
    el.setAttribute("aria-describedby", text.id);
    el.appendChild(text);

    if (hint.href) {
      var link = document.createElement("a");
      link.className = "coachmark-cta";
      link.href = hint.href;
      link.textContent = i18n("coachmarks." + hint.id + ".cta", hint.href);
      el.appendChild(link);
    }

    var meta = document.createElement("div");
    meta.className = "coachmark-meta";

    var stepLabel = document.createElement("span");
    stepLabel.className = "coachmark-step";
    stepLabel.textContent = i18n("coachmarks.step", "{current}/{total}")
      .replace("{current}", String(index + 1))
      .replace("{total}", String(total));
    meta.appendChild(stepLabel);

    var nav = document.createElement("div");
    nav.className = "coachmark-nav";

    var back = document.createElement("button");
    back.type = "button";
    back.className = "btn btn-ghost coachmark-nav-btn";
    back.textContent = i18n("coachmarks.back", "Back");
    back.disabled = index === 0;
    back.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      go(-1);
    });
    nav.appendChild(back);

    var skip = document.createElement("button");
    skip.type = "button";
    skip.className = "btn btn-ghost coachmark-nav-btn";
    skip.textContent = i18n("coachmarks.skip", "Skip");
    skip.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      skipTour();
    });
    nav.appendChild(skip);

    var last = index >= total - 1;
    var primary = document.createElement("button");
    primary.type = "button";
    primary.className = "btn btn-primary coachmark-nav-btn";
    primary.textContent = last ? i18n("coachmarks.done", "Done") : i18n("coachmarks.next", "Next");
    primary.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      if (last) finishTour();
      else go(1);
    });
    nav.appendChild(primary);

    meta.appendChild(nav);
    el.appendChild(meta);

    var close = document.createElement("button");
    close.type = "button";
    close.className = "coachmark-close";
    close.setAttribute("aria-label", i18n("coachmarks.skip", "Skip"));
    close.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      skipTour();
    });
    el.appendChild(close);

    return el;
  }

  function buildOverlay(host) {
    var overlay = document.createElement("div");
    overlay.className = "coachmark-overlay";
    if (host !== document.body) overlay.classList.add("coachmark-overlay--dialog");
    overlay.setAttribute("aria-hidden", "true");
    overlay.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    });

    var spot = document.createElement("div");
    spot.className = "coachmark-spotlight";
    overlay.appendChild(spot);
    return { overlay: overlay, spot: spot };
  }

  function bindKeys(el) {
    function onKey(ev) {
      if (!tour || tour.el !== el) return;
      if (ev.key === "Escape") {
        ev.preventDefault();
        ev.stopPropagation();
        skipTour();
        return;
      }
      if (ev.key !== "Tab") return;
      var items = focusables(el);
      if (!items.length) {
        ev.preventDefault();
        el.focus();
        return;
      }
      var first = items[0];
      var lastItem = items[items.length - 1];
      var active = document.activeElement;
      if (ev.shiftKey) {
        if (active === first || !el.contains(active)) {
          ev.preventDefault();
          lastItem.focus();
        }
      } else if (active === lastItem || !el.contains(active)) {
        ev.preventDefault();
        first.focus();
      }
    }
    tour._onKey = onKey;
    document.addEventListener("keydown", onKey, true);
  }

  function revealStable() {
    if (!tour || !tour.el || !tour.anchor) return;
    var el = tour.el;
    var host = tour.host;
    var prev = "";
    var stable = 0;
    var tries = 0;
    var id = tour.steps[tour.index].hint.id;

    function finish() {
      if (!tour || tour.el !== el) return;
      place(el, tour.anchor, host);
      placeSpotlight(tour.spot, tour.anchor, host);
      el.style.visibility = "";
      el.classList.add("is-shown");
      tour.ready = true;
      markSeen(id);
      try {
        el.focus({ preventScroll: true });
      } catch (e) {
        el.focus();
      }
    }

    function tick() {
      if (!tour || tour.el !== el) return;
      if (!document.contains(tour.anchor) || !isVisible(tour.anchor)) {
        skipMissingStep();
        return;
      }
      place(el, tour.anchor, host);
      placeSpotlight(tour.spot, tour.anchor, host);
      tries += 1;
      var key = el.style.left + "," + el.style.top + "," + (tour.spot && tour.spot.style.left) + "," + (tour.spot && tour.spot.style.top);
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

    el.style.visibility = "hidden";
    if (host === document.body && typeof el.showPopover === "function") {
      try {
        el.setAttribute("popover", "manual");
        el.showPopover();
      } catch (e) {}
    }
    requestAnimationFrame(tick);
  }

  function afterScroll(cb) {
    if (scrollWait) {
      clearTimeout(scrollWait);
      scrollWait = null;
    }
    var done = false;
    function finish() {
      if (done) return;
      done = true;
      if (scrollWait) {
        clearTimeout(scrollWait);
        scrollWait = null;
      }
      window.removeEventListener("scrollend", onEnd, true);
      cb();
    }
    function onEnd() {
      finish();
    }
    window.addEventListener("scrollend", onEnd, true);
    scrollWait = setTimeout(finish, prefersReducedMotion() ? 40 : 320);
  }

  function showStep(index) {
    if (!tour) return;
    destroyUi();
    tour.index = index;
    tour.ready = false;

    var step = tour.steps[index];
    if (!step) {
      endTour(false);
      return;
    }

    var anchor = findAnchor(step.hint.id);
    if (!anchor || (step.hint.when && !step.hint.when(anchor))) {
      skipMissingStep();
      return;
    }
    if (!i18n("coachmarks." + step.hint.id + ".body", "")) {
      skipMissingStep();
      return;
    }

    step.anchor = anchor;
    tour.anchor = anchor;
    tour.host = hostFor(anchor);
    ensureAnchorReachable(anchor);

    var layer = buildOverlay(tour.host);
    tour.overlay = layer.overlay;
    tour.spot = layer.spot;
    tour.host.appendChild(tour.overlay);

    tour.el = buildCard(step, index, tour.steps.length);
    if (tour.host !== document.body) tour.el.classList.add("coachmark--dialog");
    tour.host.appendChild(tour.el);
    bindKeys(tour.el);
    placeSpotlight(tour.spot, anchor, tour.host);

    try {
      anchor.scrollIntoView({
        behavior: prefersReducedMotion() ? "auto" : "smooth",
        block: "center",
        inline: "nearest",
      });
    } catch (e) {
      try {
        anchor.scrollIntoView(true);
      } catch (e2) {}
    }

    afterScroll(function () {
      if (!tour || tour.index !== index) return;
      revealStable();
    });
  }

  function beginTour(scope, replay) {
    if (!storageKey()) return false;
    var steps = collectSteps(scope || "", !!replay);
    if (!steps.length) return false;
    if (tour) endTour(false);
    tour = {
      scope: scope || "",
      steps: steps,
      index: 0,
      replay: !!replay,
      el: null,
      overlay: null,
      spot: null,
      host: null,
      anchor: null,
      ready: false,
      _onKey: null,
    };
    showStep(0);
    return true;
  }

  function scan() {
    if (!storageKey() || !catalog().length) return;

    if (tour) {
      if (!tour.anchor || !document.contains(tour.anchor) || !isVisible(tour.anchor)) {
        var refreshed = findAnchor(tour.steps[tour.index].hint.id);
        if (refreshed && isVisible(refreshed)) {
          var nextHost = hostFor(refreshed);
          tour.anchor = refreshed;
          tour.steps[tour.index].anchor = refreshed;
          if (nextHost !== tour.host || !tour.el || !document.contains(tour.el)) {
            showStep(tour.index);
          } else {
            scheduleSync();
          }
        } else {
          skipMissingStep();
        }
      } else {
        scheduleSync();
      }
      return;
    }

    beginTour("", false);
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

  window.__coachmarks = {
    replay: function (scope) {
      return beginTour(scope, true);
    },
  };

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
    },
    true
  );
  document.addEventListener("click", function (ev) {
    var btn = ev.target && ev.target.closest && ev.target.closest("[data-coachmark-replay]");
    if (!btn) return;
    var scope = btn.getAttribute("data-coachmark-replay");
    if (!scope) return;
    ev.preventDefault();
    beginTour(scope, true);
  });
  window.addEventListener("resize", scheduleSync, { passive: true });
  window.addEventListener("scroll", scheduleSync, { passive: true, capture: true });
})();
