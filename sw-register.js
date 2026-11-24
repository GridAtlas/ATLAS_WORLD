/* Register the Atlas World service worker from any depth of the site. */
(function () {
  if (!("serviceWorker" in navigator)) return;
  var src = document.currentScript && document.currentScript.src;
  var root;
  if (src) {
    root = src.replace(/sw-register\.js(?:\?.*)?$/, "");
  } else {
    root = new URL("./", location.href).href;
  }
  navigator.serviceWorker.register(root + "sw.js", { scope: root }).catch(function () {});
})();
