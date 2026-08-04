(function () {
  var root = document.documentElement;
  function parseList(raw) {
    if (!raw) return [];
    try {
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch (e) {
      return String(raw)
        .split(",")
        .map(function (s) {
          return s.trim();
        })
        .filter(Boolean);
    }
  }
  function applyScheme(theme, darkThemes) {
    root.setAttribute("data-scheme", darkThemes.indexOf(theme) !== -1 ? "dark" : "light");
  }
  function applyPref(key, allowed, attr) {
    try {
      var value = localStorage.getItem(key);
      if (value && allowed.indexOf(value) !== -1) {
        root.setAttribute(attr, value);
        return value;
      }
    } catch (e) {}
    return null;
  }
  var darkThemes = parseList(root.getAttribute("data-dark-themes"));
  var themeKey = root.getAttribute("data-theme-storage-key") || "";
  var themeAllowed = parseList(root.getAttribute("data-theme-ids"));
  var theme = applyPref(themeKey, themeAllowed, "data-theme") || root.getAttribute("data-theme") || "ocean";
  applyScheme(theme, darkThemes);
  try {
    var gradKey = root.getAttribute("data-theme-gradient-storage-key") || "";
    var map = JSON.parse(localStorage.getItem(gradKey) || "{}");
    var grad = map[theme];
    root.setAttribute("data-theme-gradient", grad === false || grad === "off" ? "off" : "on");
  } catch (e) {}
  applyPref(root.getAttribute("data-density-storage-key") || "", parseList(root.getAttribute("data-density-ids")), "data-density");
  applyPref(root.getAttribute("data-font-size-storage-key") || "", parseList(root.getAttribute("data-font-size-ids")), "data-font-size");
  applyPref(root.getAttribute("data-thread-order-storage-key") || "", parseList(root.getAttribute("data-thread-order-ids")), "data-thread-order");
})();
