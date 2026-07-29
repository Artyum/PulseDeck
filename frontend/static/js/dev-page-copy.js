(function () {
  const btn = document.getElementById("dev-page-copy");
  if (!btn) return;
  let info;
  try {
    info = JSON.parse(btn.getAttribute("data-dev-page-info") || "null");
  } catch (e) {
    return;
  }
  if (!info) return;

  function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (err) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  btn.addEventListener("click", function () {
    const text = JSON.stringify(info, null, 2);
    const done = function (ok) {
      const prev = btn.textContent;
      btn.classList.remove("is-ok", "is-err");
      btn.classList.add(ok ? "is-ok" : "is-err");
      btn.textContent = ok ? "OK" : "Błąd";
      setTimeout(function () {
        btn.textContent = prev;
        btn.classList.remove("is-ok", "is-err");
      }, 1200);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard
        .writeText(text)
        .then(function () {
          done(true);
        })
        .catch(function () {
          done(fallbackCopy(text));
        });
      return;
    }
    done(fallbackCopy(text));
  });
})();
