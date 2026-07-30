(function () {
  function projectsWrap(form) {
    return (
      form.querySelector("[data-projects-field]") ||
      form.querySelector("[data-edit-projects-field]")
    );
  }

  function setProjectsRequiredVisible(wrap, visible) {
    if (!wrap) return;
    const hint = wrap.querySelector("[data-projects-required]");
    if (hint) hint.hidden = !visible;
  }

  function requireProjects(form) {
    const wrap = projectsWrap(form);
    if (!wrap || wrap.hidden) return true;
    const boxes = wrap.querySelectorAll("input[name=project_ids]:not(:disabled)");
    if (!boxes.length) return true;
    const ok = Array.prototype.some.call(boxes, function (el) {
      return el.checked;
    });
    setProjectsRequiredVisible(wrap, !ok);
    return ok;
  }

  function syncNewUserProjects() {
    const root = document.getElementById("new-user");
    if (!root) return;
    const role = root.querySelector("[data-role-select]");
    const field = root.querySelector("[data-projects-field]");
    const hint = root.querySelector("[data-admin-projects-hint]");
    if (!role || !field || !hint) return;
    const sync = function () {
      const isAdmin = role.value === "ADMIN";
      field.hidden = isAdmin;
      hint.hidden = !isAdmin;
      field.querySelectorAll("input[name=project_ids]").forEach(function (el) {
        el.disabled = isAdmin;
      });
      if (isAdmin) setProjectsRequiredVisible(field, false);
    };
    role.addEventListener("change", sync);
    sync();
  }

  function fillEditUser(row) {
    const dlg = document.getElementById("edit-user");
    if (!dlg || !row) return;
    const id = row.getAttribute("data-user-id") || "";
    const firstName = row.getAttribute("data-first-name") || "";
    const lastName = row.getAttribute("data-last-name") || "";
    const email = row.getAttribute("data-email") || "";
    const phone = row.getAttribute("data-phone") || "";
    const isAdmin = row.getAttribute("data-is-admin") === "1";
    const isPending = row.getAttribute("data-is-pending") === "1";
    const projectIds = (row.getAttribute("data-project-ids") || "")
      .split(",")
      .filter(Boolean);

    const subtitle = dlg.querySelector("[data-edit-subtitle]");
    if (subtitle) {
      subtitle.textContent = (firstName + " " + lastName).trim() + " · " + email;
    }

    const profile = dlg.querySelector("[data-edit-profile]");
    const password = dlg.querySelector("[data-edit-password]");
    const activationForm = dlg.querySelector("[data-edit-activation-form]");
    if (profile) profile.action = "/admin/users/" + id;
    if (password) password.action = "/admin/users/" + id + "/password";
    if (activationForm) activationForm.action = "/admin/users/" + id + "/resend-activation";

    const firstEl = dlg.querySelector("#edit-user-first-name");
    const lastEl = dlg.querySelector("#edit-user-last-name");
    const emailEl = dlg.querySelector("#edit-user-email");
    const phoneEl = dlg.querySelector("#edit-user-phone");
    if (firstEl) firstEl.value = firstName;
    if (lastEl) lastEl.value = lastName;
    if (emailEl) emailEl.value = email;
    if (phoneEl) phoneEl.value = phone;

    const projectsField = dlg.querySelector("[data-edit-projects-field]");
    const adminHint = dlg.querySelector("[data-edit-admin-hint]");
    if (projectsField) {
      projectsField.hidden = isAdmin;
      projectsField.querySelectorAll("input[name=project_ids]").forEach(function (el) {
        el.disabled = isAdmin;
        el.checked = projectIds.indexOf(el.value) !== -1;
      });
      setProjectsRequiredVisible(projectsField, false);
    }
    if (adminHint) adminHint.hidden = !isAdmin;

    const activation = dlg.querySelector("[data-edit-activation]");
    if (activation) activation.hidden = !isPending;

    const linkActivation = dlg.querySelector("[data-edit-link-activation]");
    const linkReset = dlg.querySelector("[data-edit-link-reset]");
    if (linkActivation) linkActivation.hidden = !isPending;
    if (linkReset) linkReset.hidden = isPending;

    if (password) {
      password.querySelectorAll('input[type="password"]').forEach(function (el) {
        el.value = "";
      });
    }

    dlg.showModal();
  }

  function openEditFrom(el) {
    const row = el.closest("[data-user-edit]");
    if (row) fillEditUser(row);
  }

  document.querySelectorAll("[data-open-edit-user]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      openEditFrom(btn);
    });
  });

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
    const wrap = input.closest("[data-projects-field], [data-edit-projects-field]");
    if (!wrap) return;
    const boxes = wrap.querySelectorAll("input[name=project_ids]:not(:disabled)");
    const ok = Array.prototype.some.call(boxes, function (el) {
      return el.checked;
    });
    if (ok) setProjectsRequiredVisible(wrap, false);
  });

  syncNewUserProjects();

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
  if (boot.editId != null) {
    const row = document.querySelector('[data-user-edit][data-user-id="' + boot.editId + '"]');
    if (row) fillEditUser(row);
  }
  if (boot.flash || boot.editId != null) {
    history.replaceState(null, "", location.pathname);
  } else if (new URLSearchParams(location.search).get("new") === "1") {
    const dlg = document.getElementById("new-user");
    if (dlg) dlg.showModal();
    history.replaceState(null, "", location.pathname);
  }
})();
