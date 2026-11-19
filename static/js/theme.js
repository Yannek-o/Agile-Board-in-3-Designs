/* Runs synchronously in <head>: applies the stored theme before first paint. */
(function () {
  "use strict";
  var root = document.documentElement;
  var stored = null;
  try { stored = window.localStorage.getItem("ab-theme"); } catch (error) { stored = null; }
  var prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  var theme = stored === "light" || stored === "dark" ? stored : (prefersLight ? "light" : "dark");
  root.setAttribute("data-theme", theme);
  root.setAttribute("data-bs-theme", theme);
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduceMotion) { root.classList.add("motion"); }
})();
