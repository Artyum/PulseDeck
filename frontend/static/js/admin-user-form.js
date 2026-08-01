(function () {
  function clearInvalid(root) {
    if (!root) return;
    root.querySelectorAll('[aria-invalid="true"]').forEach(function (el) {
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  function syncRoleProjects(root) {
    if (!root) return;
    const role = root.querySelector("[data-role-select]");
    const field = root.querySelector("[data-projects-field]");
    const hint = root.querySelector("[data-admin-projects-hint]");
    if (!role || !field) return;
    const sync = function () {
      const isAdmin = role.value === "ADMIN";
      field.hidden = isAdmin;
      if (hint) hint.hidden = !isAdmin;
      field.querySelectorAll("input[name=project_ids]").forEach(function (el) {
        el.disabled = isAdmin;
      });
      if (isAdmin) clearInvalid(field);
    };
    role.addEventListener("change", sync);
    sync();
  }

  document.addEventListener("change", function (ev) {
    const input = ev.target;
    if (!(input instanceof HTMLInputElement) || input.name !== "project_ids") return;
    const wrap = input.closest("[data-projects-field]");
    if (!wrap) return;
    const boxes = wrap.querySelectorAll("input[name=project_ids]:not(:disabled)");
    const ok = Array.prototype.some.call(boxes, function (el) {
      return el.checked;
    });
    if (ok) clearInvalid(wrap);
  });

  document.querySelectorAll("[data-role-select]").forEach(function (el) {
    syncRoleProjects(el.closest("form, dialog") || el.parentElement);
  });

  const params = new URLSearchParams(location.search);
  if (params.get("ok")) {
    history.replaceState(null, "", location.pathname);
  } else if (params.get("new") === "1") {
    const dlg = document.getElementById("new-user");
    if (dlg) dlg.showModal();
    history.replaceState(null, "", location.pathname);
  }
})();
