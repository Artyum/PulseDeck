function speechRecognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function dictateLang() {
  var raw = (document.documentElement.getAttribute("lang") || "").trim().toLowerCase();
  if (raw.indexOf("en") === 0) return "en-US";
  return "pl-PL";
}

function setListeningUi(btn, on) {
  btn.classList.toggle("is-listening", on);
  btn.setAttribute("aria-pressed", on ? "true" : "false");
  var label = btn.getAttribute(on ? "data-label-stop" : "data-label-start");
  btn.setAttribute("aria-label", label);
  btn.setAttribute("title", label);
}

function toast(key) {
  var message = (window.__i18n || {})[key];
  if (message && typeof window.showToast === "function") window.showToast(message, "error");
}

async function collectDiagnostics() {
  var out = {
    secure: !!window.isSecureContext,
    speech: !!speechRecognitionCtor(),
    mediaDevices: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
    permissions: null,
    mic: null,
    micError: null,
    permissionsPolicy: null,
  };
  try {
    out.permissions = (await navigator.permissions.query({ name: "microphone" })).state;
  } catch (e) {
    out.permissions = "unsupported: " + e.message;
  }
  try {
    var res = await fetch(window.location.href, { method: "HEAD", credentials: "same-origin" });
    out.permissionsPolicy = res.headers.get("permissions-policy") || res.headers.get("Permissions-Policy");
  } catch (e) {
    out.permissionsPolicy = "fetch failed: " + e.message;
  }
  if (!out.mediaDevices) {
    out.micError = "mediaDevices unavailable";
    return out;
  }
  try {
    var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    var track = stream.getAudioTracks()[0];
    out.mic = track && track.label ? track.label : "ok";
    stream.getTracks().forEach(function (t) {
      t.stop();
    });
  } catch (e) {
    out.micError = (e && e.name ? e.name : "Error") + ": " + (e && e.message ? e.message : "unknown");
  }
  return out;
}

function formatDiagnostics(diag, speechError) {
  var lines = [
    "secure: " + diag.secure,
    "speech: " + diag.speech,
    "mediaDevices: " + diag.mediaDevices,
    "permissions: " + diag.permissions,
    diag.mic ? "mic: " + diag.mic : "mic: " + diag.micError,
    "permissions-policy: " + (diag.permissionsPolicy || "(none)"),
  ];
  if (speechError) lines.unshift("speech error: " + speechError);
  return lines.join("\n");
}

var diagDialog = null;

function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text).then(function () {
      return true;
    });
  }
  var ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  var ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (_e) {}
  document.body.removeChild(ta);
  return Promise.resolve(ok);
}

function ensureDiagDialog() {
  if (diagDialog) return diagDialog;
  var dlg = document.createElement("dialog");
  dlg.className = "modal dictation-diag";
  dlg.id = "dictation-diag";
  dlg.innerHTML =
    '<div class="modal-form">' +
    '<div class="modal-header">' +
    '<h2 class="modal-title">Dictation debug</h2>' +
    '<button type="button" class="modal-close" data-dictation-diag-close aria-label="Close">×</button>' +
    "</div>" +
    '<div class="modal-body">' +
    '<textarea class="dictation-diag-output" rows="10" readonly spellcheck="false"></textarea>' +
    "</div>" +
    '<div class="modal-footer">' +
    '<button type="button" class="btn btn-secondary" data-dictation-diag-close>Close</button>' +
    '<button type="button" class="btn btn-primary" data-dictation-diag-copy>Copy</button>' +
    "</div>" +
    "</div>";
  document.body.appendChild(dlg);
  dlg.querySelectorAll("[data-dictation-diag-close]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      dlg.close();
    });
  });
  var copyBtn = dlg.querySelector("[data-dictation-diag-copy]");
  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      var out = dlg.querySelector(".dictation-diag-output");
      var text = out ? out.value : "";
      var prev = copyBtn.textContent;
      copyText(text).then(function (ok) {
        copyBtn.textContent = ok ? "Copied" : "Copy failed";
        setTimeout(function () {
          copyBtn.textContent = prev;
        }, 1200);
      });
    });
  }
  diagDialog = dlg;
  return dlg;
}

function openDictationDiagnostics(text) {
  var dlg = ensureDiagDialog();
  var out = dlg.querySelector(".dictation-diag-output");
  if (out) {
    out.value = text;
    out.focus();
    out.select();
  }
  if (typeof dlg.showModal === "function") dlg.showModal();
}

function showDictationDiagnostics(speechError) {
  return collectDiagnostics().then(function (diag) {
    window.__lastDictationDiag = diag;
    openDictationDiagnostics(formatDiagnostics(diag, speechError));
    return diag;
  });
}

function reportDictationError(code) {
  showDictationDiagnostics(code || "unknown");
  if (code === "not-allowed") toast("editor.dictate_denied");
  else if (code === "audio-capture") toast("editor.dictate_no_mic");
  else if (code === "network") toast("editor.dictate_network");
}

export function attachDictation(root, editor) {
  var btn = root && root.querySelector("[data-rich-dictate]");
  if (!btn || !editor) return null;

  var Ctor = speechRecognitionCtor();
  if (!Ctor) {
    btn.hidden = true;
    return null;
  }

  btn.hidden = false;
  setListeningUi(btn, false);

  var recognition = null;
  var lastTapAt = 0;

  function stop() {
    setListeningUi(btn, false);
    if (!recognition) return;
    try {
      recognition.stop();
    } catch (_e) {}
    recognition = null;
  }

  function start() {
    if (recognition) return stop();
    if (!window.isSecureContext) {
      reportDictationError("blocked: not secure context");
      return;
    }
    recognition = new Ctor();
    recognition.lang = dictateLang();
    recognition.continuous = true;
    recognition.interimResults = false;
    setListeningUi(btn, true);

    recognition.onresult = function (ev) {
      for (var i = ev.resultIndex; i < ev.results.length; i++) {
        var result = ev.results[i];
        if (!result || !result.isFinal) continue;
        var piece = result[0] && result[0].transcript ? result[0].transcript : "";
        if (piece)
          editor
            .chain()
            .focus()
            .insertContent(piece + " ")
            .run();
      }
    };

    recognition.onerror = function (ev) {
      var code = ev && ev.error ? String(ev.error) : "";
      reportDictationError(code || "unknown");
      stop();
    };

    recognition.onend = function () {
      recognition = null;
      setListeningUi(btn, false);
    };

    try {
      recognition.start();
    } catch (_e) {
      stop();
      reportDictationError("start failed");
    }
  }

  function onToggle(ev) {
    ev.preventDefault();
    start();
  }

  function onDebugTrigger(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    showDictationDiagnostics();
  }

  function onTouchEnd(ev) {
    var now = Date.now();
    if (now - lastTapAt < 400) {
      ev.preventDefault();
      lastTapAt = 0;
      showDictationDiagnostics();
      return;
    }
    lastTapAt = now;
  }

  btn.addEventListener("click", onToggle);
  btn.addEventListener("dblclick", onDebugTrigger);
  btn.addEventListener("touchend", onTouchEnd);

  var api = {
    stop: stop,
    destroy: function () {
      stop();
      btn.removeEventListener("click", onToggle);
      btn.removeEventListener("dblclick", onDebugTrigger);
      btn.removeEventListener("touchend", onTouchEnd);
      setListeningUi(btn, false);
    },
  };
  root._richDictation = api;
  return api;
}

export function detachDictation(root) {
  if (!root || !root._richDictation) return;
  try {
    root._richDictation.destroy();
  } catch (_e) {}
  root._richDictation = null;
}

export function stopDictation(root) {
  if (root && root._richDictation && typeof root._richDictation.stop === "function") {
    root._richDictation.stop();
  }
}
