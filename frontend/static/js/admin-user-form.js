(function () {
  const role = document.querySelector("[data-role-select]");
  const field = document.querySelector("[data-projects-field]");
  const hint = document.querySelector("[data-admin-projects-hint]");
  if (!role || !field || !hint) return;
  const sync = function () {
    const isAdmin = role.value === "ADMIN";
    field.hidden = isAdmin;
    hint.hidden = !isAdmin;
    field.querySelectorAll("input[name=project_ids]").forEach(function (el) {
      el.disabled = isAdmin;
    });
  };
  role.addEventListener("change", sync);
  sync();
})();
