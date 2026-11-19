/* Floating navigation bar: sliding glow indicator and mobile menu toggle. */
(function () {
  "use strict";

  var STORAGE_KEY = "ab-nav-indicator";

  function initIndicator(nav) {
    var indicator = nav.querySelector(".ab-nav-indicator");
    if (!indicator) { return; }
    var active = nav.querySelector("a.active");
    nav.classList.add("has-indicator");

    function place(link, animate) {
      if (!link || !link.offsetWidth) {
        indicator.classList.remove("is-visible");
        return;
      }
      if (!animate) { indicator.classList.add("no-transition"); }
      nav.style.setProperty("--ab-ind-x", link.offsetLeft + "px");
      nav.style.setProperty("--ab-ind-w", link.offsetWidth + "px");
      indicator.classList.add("is-visible");
      if (!animate) {
        void indicator.offsetWidth;
        indicator.classList.remove("no-transition");
      }
    }

    function remember() {
      if (!active) { return; }
      try {
        window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
          x: active.offsetLeft, w: active.offsetWidth
        }));
      } catch (error) { /* storage unavailable */ }
    }

    var previous = null;
    try { previous = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || "null"); } catch (error) { previous = null; }
    var motion = document.documentElement.classList.contains("motion");
    if (previous && active && motion) {
      indicator.classList.add("no-transition", "is-visible");
      nav.style.setProperty("--ab-ind-x", previous.x + "px");
      nav.style.setProperty("--ab-ind-w", previous.w + "px");
      void indicator.offsetWidth;
      indicator.classList.remove("no-transition");
      window.requestAnimationFrame(function () { place(active, true); });
    } else {
      place(active, false);
    }
    remember();

    nav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("mouseenter", function () { place(link, true); });
      link.addEventListener("focus", function () { place(link, true); });
    });
    nav.addEventListener("mouseleave", function () { place(active, true); });
    nav.addEventListener("focusout", function (event) {
      if (!nav.contains(event.relatedTarget)) { place(active, true); }
    });
    window.addEventListener("resize", function () { place(active, false); remember(); });
  }

  function initToggle(nav) {
    var toggle = document.querySelector('.ab-nav-toggle[aria-controls="' + nav.id + '"]');
    if (!toggle) { return; }

    function setOpen(open) {
      nav.classList.toggle("open", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "Menü schließen" : "Menü öffnen");
    }

    toggle.addEventListener("click", function () {
      setOpen(!nav.classList.contains("open"));
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && nav.classList.contains("open")) {
        setOpen(false);
        toggle.focus();
      }
    });
    document.addEventListener("click", function (event) {
      if (nav.classList.contains("open") && !nav.contains(event.target) && !toggle.contains(event.target)) {
        setOpen(false);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var nav = document.getElementById("ab-primary-nav");
    initBell(document.querySelector(".ab-bell[data-unread-url]"));
    if (!nav) { return; }
    initIndicator(nav);
    initToggle(nav);
  });

  function initBell(bell) {
    if (!bell) { return; }
    var badge = bell.querySelector(".ab-bell-count");
    var last = Number(badge.textContent) || 0;

    function update(count) {
      badge.textContent = String(count);
      badge.hidden = count === 0;
      bell.setAttribute("aria-label", "Benachrichtigungen, " + count + " ungelesen");
      if (count > last) {
        bell.classList.remove("ring");
        void bell.offsetWidth;
        bell.classList.add("ring");
      }
      last = count;
    }

    function poll() {
      if (document.hidden) { return; }
      fetch(bell.dataset.unreadUrl, { credentials: "same-origin", cache: "no-store", headers: { "Accept": "application/json" } })
        .then(function (response) { return response.ok ? response.json() : null; })
        .then(function (data) { if (data) { update(data.count); } })
        .catch(function () { /* offline: retry later */ });
    }

    window.setInterval(poll, 30000);
    document.addEventListener("visibilitychange", poll);
  }
})();
