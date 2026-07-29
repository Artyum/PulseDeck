(function () {
  const dlg = document.getElementById("img-lightbox");
  if (!dlg) return;
  const img = dlg.querySelector("img");
  document.addEventListener("click", function (ev) {
    const btn = ev.target.closest("[data-lightbox-src]");
    if (!btn) return;
    ev.preventDefault();
    img.src = btn.getAttribute("data-lightbox-src") || "";
    img.alt = btn.getAttribute("data-lightbox-alt") || "";
    dlg.showModal();
  });
  dlg.addEventListener("click", function (ev) {
    if (ev.target === dlg) dlg.close();
  });
  dlg.addEventListener("close", function () {
    img.removeAttribute("src");
    img.alt = "";
  });
})();
