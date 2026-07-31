(function () {
  function setProjectsRequiredVisible(wrap, visible) {
    if (!wrap) return;
    const hint = wrap.querySelector("[data-projects-required]");
    if (hint) hint.hidden = !visible;
  }

  function requireProjects(form) {
    const wrap = form.querySelector("[data-projects-field]");
    if (!wrap || wrap.hidden) return true;
    const boxes = wrap.querySelectorAll("input[name=project_ids]:not(:disabled)");
    if (!boxes.length) return true;
    const ok = Array.prototype.some.call(boxes, function (el) {
      return el.checked;
    });
    setProjectsRequiredVisible(wrap, !ok);
    return ok;
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
      if (isAdmin) setProjectsRequiredVisible(field, false);
    };
    role.addEventListener("change", sync);
    sync();
  }

  document.addEventListener(
    "submit",
    function (ev) {
      const form = ev.target;
      if (!(form instanceof HTMLFormElement)) return;
      if (!requireProjects(form)) {
        ev.preventDefault();
        ev.stopImmediatePropagation();
      }
    },
    true
  );

  document.addEventListener("change", function (ev) {
    const input = ev.target;
    if (!(input instanceof HTMLInputElement) || input.name !== "project_ids") return;
    const wrap = input.closest("[data-projects-field]");
    if (!wrap) return;
    const boxes = wrap.querySelectorAll("input[name=project_ids]:not(:disabled)");
    const ok = Array.prototype.some.call(boxes, function (el) {
      return el.checked;
    });
    if (ok) setProjectsRequiredVisible(wrap, false);
  });

  document.querySelectorAll("[data-role-select]").forEach(function (el) {
    syncRoleProjects(el.closest("form, dialog") || el.parentElement);
  });

  const bootEl = document.getElementById("admin-users-boot");
  let boot = {};
  if (bootEl) {
    try {
      boot = JSON.parse(bootEl.textContent || "{}") || {};
    } catch (e) {
      boot = {};
    }
  }
  if (boot.flash && typeof window.showToast === "function") {
    window.showToast(String(boot.flash), "success");
  }
  if (boot.flash) {
    history.replaceState(null, "", location.pathname);
  } else if (new URLSearchParams(location.search).get("new") === "1") {
    const dlg = document.getElementById("new-user");
    if (dlg) dlg.showModal();
    history.replaceState(null, "", location.pathname);
  }
})();
