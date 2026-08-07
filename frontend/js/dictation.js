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

function reportSpeechError(code) {
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
      toast("editor.dictate_denied");
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
      if (code !== "no-speech" && code !== "aborted") reportSpeechError(code);
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
      toast("editor.dictate_network");
    }
  }

  function onToggle(ev) {
    ev.preventDefault();
    start();
  }

  btn.addEventListener("click", onToggle);

  var api = {
    stop: stop,
    destroy: function () {
      stop();
      btn.removeEventListener("click", onToggle);
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
