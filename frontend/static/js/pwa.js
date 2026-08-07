(function () {
  if (!window.isSecureContext || !("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
})();
