(function () {
  function pathIs(re) {
    return re.test(location.pathname || "");
  }

  function feedPath() {
    return pathIs(/^\/p\/[^/]+\/?$/);
  }

  function ticketPath() {
    return pathIs(/^\/t\/[^/]+\/?$/);
  }

  window.__coachmarkCatalog = [
    { id: "nav-appearance", href: "/profile/appearance" },
    { id: "nav-admin", href: "/admin" },
    { id: "nav-project" },
    {
      id: "feed-create",
      match: feedPath,
    },
    {
      id: "feed-needs-us",
      match: feedPath,
    },
    {
      id: "feed-waiting-on-me",
      match: feedPath,
    },
    {
      id: "feed-unassigned",
      match: feedPath,
    },
    {
      id: "feed-mine",
      match: feedPath,
    },
    {
      id: "feed-filters",
      match: feedPath,
    },
    {
      id: "ticket-status",
      match: ticketPath,
    },
    {
      id: "ticket-done",
      match: ticketPath,
    },
    {
      id: "ticket-reopen",
      match: ticketPath,
    },
    {
      id: "ticket-priority",
      match: ticketPath,
    },
    {
      id: "ticket-assignee",
      match: ticketPath,
    },
    {
      id: "ticket-self-assign",
      match: ticketPath,
    },
    {
      id: "ticket-add-participant",
      match: ticketPath,
    },
    {
      id: "ticket-participants",
      match: ticketPath,
    },
    {
      id: "ticket-tags",
      match: ticketPath,
    },
    {
      id: "profile-notifications",
      match: function () {
        return pathIs(/^\/profile\/notifications\/?$/);
      },
    },
    {
      id: "admin-projects",
      match: function () {
        return pathIs(/^\/admin\/projects\/?$/);
      },
    },
    {
      id: "admin-project-tags",
      match: function () {
        return pathIs(/^\/admin\/projects\/?$/);
      },
    },
    {
      id: "admin-project-members",
      match: function () {
        return pathIs(/^\/admin\/projects\/[^/]+\/?$/);
      },
    },
    {
      id: "admin-users-new",
      match: function () {
        return pathIs(/^\/admin\/users\/?$/);
      },
    },
    {
      id: "admin-settings-tickets",
      match: function () {
        return pathIs(/^\/admin\/settings\/tickets\/?$/);
      },
    },
    {
      id: "admin-settings-uploads",
      match: function () {
        return pathIs(/^\/admin\/settings\/uploads\/?$/);
      },
    },
    {
      id: "admin-mail",
      match: function () {
        return pathIs(/^\/admin\/settings\/mail\/?$/);
      },
      when: function (el) {
        return !String((el && el.value) || "").trim();
      },
    },
    { id: "compose-attach" },
    { id: "compose-quote" },
    { id: "compose-internal" },
  ];
})();
