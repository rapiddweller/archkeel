/* ArchKeel theme switch. Inline in <head>, before the stylesheets, so the first paint has the right theme. */
(function () {
  var KEY = "archkeel-theme", root = document.documentElement;
  function stored() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function sync(t) {
    root.setAttribute("data-theme", t);
    var b = document.querySelectorAll("[data-ak-theme]");
    for (var i = 0; i < b.length; i++) {
      b[i].setAttribute("aria-pressed", String(b[i].getAttribute("data-ak-theme") === t));
    }
  }
  var t = stored();
  if (t !== "light" && t !== "dark") {
    t = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }
  root.setAttribute("data-theme", t);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { sync(t); });
  } else {
    sync(t);
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-ak-theme]");
    if (!b) return;
    var n = b.getAttribute("data-ak-theme");
    try { localStorage.setItem(KEY, n); } catch (err) { /* storage blocked: choice lasts for this page */ }
    sync(n);
  });
})();
