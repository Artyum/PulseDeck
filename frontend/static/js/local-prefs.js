(function () {
  var FEED_FILTERS_KEY = "pulsedeck.feedFiltersByProject";
  var FEED_DEFAULTS = { sort: "created_at", per_page: "25" };
  var FEED_FIELDS = ["view", "mine", "mine_paused", "priority", "type", "status", "tag", "q", "sort", "per_page"];
  var FEED_QUERY_KEYS = ["priority", "type", "status", "tag", "q", "sort", "per_page"];

  function getItem(key, fallback) {
    if (!key) return fallback;
    try {
      var value = localStorage.getItem(key);
      return value == null ? fallback : value;
    } catch (e) {
      return fallback;
    }
  }

  function setItem(key, value) {
    if (!key) return;
    try {
      localStorage.setItem(key, value);
    } catch (e) {}
  }

  function readJsonObject(key) {
    try {
      var parsed = JSON.parse(localStorage.getItem(key) || "{}");
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  function writeJsonObject(key, obj) {
    setItem(key, JSON.stringify(obj && typeof obj === "object" ? obj : {}));
  }

  function flagOn(value) {
    var v = String(value || "").toLowerCase();
    return v === "1" || v === "true" || v === "on";
  }

  function projectKeyFrom(el) {
    return ((el && el.getAttribute("data-project-key")) || "").trim().toUpperCase();
  }

  function feedStateFromParams(params) {
    var state = {};
    FEED_FIELDS.forEach(function (name) {
      var raw = (params.get(name) || "").trim();
      if (!raw) return;
      if (name === "mine" || name === "mine_paused") {
        if (flagOn(raw)) state[name] = "1";
        return;
      }
      if (FEED_DEFAULTS[name] && raw === FEED_DEFAULTS[name]) return;
      state[name] = raw;
    });
    return state;
  }

  function buildFeedUrl(projectKey, state) {
    var params = new URLSearchParams();
    params.set("view", (state && state.view) || "all");
    if (state && state.mine === "1") params.set("mine", "1");
    else if (state && state.mine_paused === "1") params.set("mine_paused", "1");
    FEED_QUERY_KEYS.forEach(function (name) {
      if (state && state[name]) params.set(name, state[name]);
    });
    return "/p/" + projectKey + "?" + params.toString();
  }

  function saveFeedState(projectKey, state) {
    var map = readJsonObject(FEED_FILTERS_KEY);
    if (state && Object.keys(state).length) map[projectKey] = state;
    else delete map[projectKey];
    writeJsonObject(FEED_FILTERS_KEY, map);
  }

  function syncFeedFilters() {
    var form = document.getElementById("feed-filters");
    var projectKey = projectKeyFrom(form);
    if (!projectKey) return;
    var params = new URLSearchParams(window.location.search);
    if (params.toString()) {
      saveFeedState(projectKey, feedStateFromParams(params));
      return;
    }
    var stored = readJsonObject(FEED_FILTERS_KEY)[projectKey];
    if (stored && typeof stored === "object" && Object.keys(stored).length) {
      window.location.replace(buildFeedUrl(projectKey, stored));
    }
  }

  function onReady(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  onReady(syncFeedFilters);
  document.addEventListener("htmx:afterSwap", function (ev) {
    var target = ev.detail && ev.detail.target;
    if (!target) return;
    if (target.id === "feed-header-and-results" || target.querySelector("#feed-filters")) {
      syncFeedFilters();
    }
  });
  document.addEventListener("htmx:pushedIntoHistory", syncFeedFilters);
  document.addEventListener("click", function (ev) {
    if (!ev.target.closest("[data-feed-filter-clear]")) return;
    var projectKey = projectKeyFrom(ev.target.closest("#feed-filters"));
    if (projectKey) saveFeedState(projectKey, null);
  });

  window.pulseDeckLocalPrefs = {
    getItem: getItem,
    setItem: setItem,
    readJsonObject: readJsonObject,
    writeJsonObject: writeJsonObject,
  };
})();
