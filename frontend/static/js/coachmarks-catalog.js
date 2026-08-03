(function () {
  function pathIs(re) {
    return re.test(location.pathname || "");
  }

  window.__coachmarkCatalog = [
    { id: "nav-appearance", href: "/profile/appearance" },
    { id: "nav-project" },
    { id: "feed-create", match: function () { return pathIs(/^\/p\/[^/]+\/?$/); } },
    { id: "ticket-status", match: function () { return pathIs(/^\/t\/[^/]+\/?$/); } },
    { id: "profile-notifications", match: function () { return pathIs(/^\/profile\/notifications\/?$/); } },
    { id: "admin-projects", match: function () { return pathIs(/^\/admin\/projects\/?$/); } },
    {
      id: "admin-mail",
      match: function () { return pathIs(/^\/admin\/settings\/mail\/?$/); },
      when: function (el) { return !String(el && el.value || "").trim(); },
    },
    { id: "compose-attach" },
  ];
})();
