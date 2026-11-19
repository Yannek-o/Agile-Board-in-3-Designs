/* Visual effects: theme switch, particles, count-up, spotlight/tilt, ripple. */
(function () {
  "use strict";

  var root = document.documentElement;

  function motionAllowed() {
    return root.classList.contains("motion");
  }

  /* ---------- Theme toggle ---------- */

  function currentTheme() {
    return root.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function labelToggles() {
    var next = currentTheme() === "light" ? "dunkles" : "helles";
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.setAttribute("aria-label", "Zu " + next + " Design wechseln");
      button.setAttribute("title", "Zu " + next + " Design wechseln");
    });
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-bs-theme", theme);
    try { window.localStorage.setItem("ab-theme", theme); } catch (error) { /* private mode */ }
    labelToggles();
    document.dispatchEvent(new CustomEvent("ab:themechange", { detail: { theme: theme } }));
  }

  function initThemeToggle() {
    labelToggles();
    document.addEventListener("click", function (event) {
      var button = event.target.closest("[data-theme-toggle]");
      if (!button) { return; }
      var next = currentTheme() === "light" ? "dark" : "light";
      if (!motionAllowed() || !document.startViewTransition) {
        applyTheme(next);
        return;
      }
      var rect = button.getBoundingClientRect();
      root.style.setProperty("--ab-reveal-x", (rect.left + rect.width / 2) + "px");
      root.style.setProperty("--ab-reveal-y", (rect.top + rect.height / 2) + "px");
      root.classList.add("theme-switching");
      var transition = document.startViewTransition(function () { applyTheme(next); });
      transition.finished.then(function () { root.classList.remove("theme-switching"); });
    });
  }

  /* ---------- Particle network ---------- */

  function initParticles() {
    var canvas = document.querySelector(".ab-particles");
    if (!canvas || !motionAllowed() || !canvas.getContext) { return; }
    var design = root.getAttribute("data-design");
    if (design === "patina" || design === "kalt") { return; }
    var context = canvas.getContext("2d");
    var particles = [];
    var pointer = { x: -9999, y: -9999 };
    var colors = [];
    var width = 0;
    var height = 0;
    var ratio = Math.min(window.devicePixelRatio || 1, 2);
    var frame = null;

    function readColors() {
      var style = getComputedStyle(root);
      colors = [
        style.getPropertyValue("--ab-particle-1").trim() || "255,107,0",
        style.getPropertyValue("--ab-particle-2").trim() || "139,92,246"
      ];
    }

    function resize() {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      var count = Math.min(70, Math.round((width * height) / 22000));
      particles = [];
      for (var index = 0; index < count; index++) {
        particles.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.35,
          vy: (Math.random() - 0.5) * 0.35,
          r: Math.random() * 1.6 + 0.6,
          c: index % 3 === 0 ? 1 : 0
        });
      }
    }

    function step() {
      context.clearRect(0, 0, width, height);
      for (var i = 0; i < particles.length; i++) {
        var p = particles[i];
        var dx = pointer.x - p.x;
        var dy = pointer.y - p.y;
        var distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < 160) {
          p.vx += dx / distance * 0.012;
          p.vy += dy / distance * 0.012;
        }
        p.vx *= 0.99;
        p.vy *= 0.99;
        p.x += p.vx + (Math.random() - 0.5) * 0.05;
        p.y += p.vy + (Math.random() - 0.5) * 0.05;
        if (p.x < 0 || p.x > width) { p.vx *= -1; }
        if (p.y < 0 || p.y > height) { p.vy *= -1; }
        context.beginPath();
        context.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        context.fillStyle = "rgba(" + colors[p.c] + ",0.85)";
        context.fill();
        for (var j = i + 1; j < particles.length; j++) {
          var q = particles[j];
          var lx = p.x - q.x;
          var ly = p.y - q.y;
          var link = lx * lx + ly * ly;
          if (link < 16900) {
            context.beginPath();
            context.moveTo(p.x, p.y);
            context.lineTo(q.x, q.y);
            context.strokeStyle = "rgba(" + colors[p.c] + "," + (0.22 * (1 - link / 16900)) + ")";
            context.lineWidth = 0.7;
            context.stroke();
          }
        }
      }
      frame = window.requestAnimationFrame(step);
    }

    function start() { if (frame === null) { frame = window.requestAnimationFrame(step); } }
    function stop() { if (frame !== null) { window.cancelAnimationFrame(frame); frame = null; } }

    readColors();
    resize();
    start();
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", function (event) { pointer.x = event.clientX; pointer.y = event.clientY; });
    window.addEventListener("pointerleave", function () { pointer.x = -9999; pointer.y = -9999; });
    document.addEventListener("visibilitychange", function () { if (document.hidden) { stop(); } else { start(); } });
    document.addEventListener("ab:themechange", readColors);
  }

  /* ---------- Count-up for key figures ---------- */

  function initCountUp() {
    if (!motionAllowed()) { return; }
    document.querySelectorAll(".ab-tile .value").forEach(function (element) {
      var template = element.textContent;
      var numbers = template.match(/\d+(?:[.,]\d+)?/g);
      if (!numbers) { return; }
      var targets = numbers.map(function (n) { return parseFloat(n.replace(",", ".")); });
      var decimals = numbers.map(function (n) { var part = n.split(/[.,]/)[1]; return part ? part.length : 0; });
      var duration = 1300;
      var startTime = null;

      function render(progress) {
        var eased = 1 - Math.pow(1 - progress, 3);
        var index = 0;
        element.textContent = template.replace(/\d+(?:[.,]\d+)?/g, function () {
          var value = (targets[index] * eased).toFixed(decimals[index]).replace(".", ",");
          index += 1;
          return value;
        });
      }

      function tick(timestamp) {
        if (startTime === null) { startTime = timestamp; }
        var progress = Math.min((timestamp - startTime) / duration, 1);
        render(progress);
        if (progress < 1) { window.requestAnimationFrame(tick); } else { element.textContent = template; }
      }

      render(0);
      window.requestAnimationFrame(tick);
    });
  }

  /* ---------- Staggered entrance ---------- */

  function initStagger() {
    var selector = ".ab-content .ab-tile, .ab-content .ab-card, .ab-content .ab-table-wrap, .ab-content .project-card, .ab-content .board-column, .ab-content .ab-goal";
    document.querySelectorAll(selector).forEach(function (element, index) {
      element.style.setProperty("--ab-i", String(Math.min(index, 14)));
    });
  }

  /* ---------- Spotlight + 3D tilt ---------- */

  function initSpotlight() {
    if (!motionAllowed() || !window.matchMedia("(hover: hover)").matches) { return; }
    var selector = ".ab-card, .ab-tile, .project-card, .board-card, .plan-item";
    document.addEventListener("pointermove", function (event) {
      var target = event.target.closest(selector);
      if (!target) { return; }
      var rect = target.getBoundingClientRect();
      var x = event.clientX - rect.left;
      var y = event.clientY - rect.top;
      target.style.setProperty("--ab-mx", x + "px");
      target.style.setProperty("--ab-my", y + "px");
      if (target.matches(".ab-tile, .project-card")) {
        var rotateY = ((x / rect.width) - 0.5) * 8;
        var rotateX = (0.5 - (y / rect.height)) * 8;
        target.style.setProperty("--ab-rx", rotateX.toFixed(2) + "deg");
        target.style.setProperty("--ab-ry", rotateY.toFixed(2) + "deg");
      }
    });
    document.addEventListener("pointerout", function (event) {
      var target = event.target.closest(".ab-tile, .project-card");
      if (target && !target.contains(event.relatedTarget)) {
        target.style.setProperty("--ab-rx", "0deg");
        target.style.setProperty("--ab-ry", "0deg");
      }
    });
  }

  /* ---------- Ripple on buttons ---------- */

  function initRipple() {
    if (!motionAllowed()) { return; }
    document.addEventListener("pointerdown", function (event) {
      var button = event.target.closest(
        ".btn, .ab-theme-toggle, .ab-user-button, .ab-nav-toggle, .filter-chip, .ab-tabs a"
      );
      if (!button) { return; }
      var rect = button.getBoundingClientRect();
      var ripple = document.createElement("span");
      var size = Math.max(rect.width, rect.height) * 2;
      ripple.className = "ab-ripple";
      ripple.style.width = ripple.style.height = size + "px";
      ripple.style.left = (event.clientX - rect.left - size / 2) + "px";
      ripple.style.top = (event.clientY - rect.top - size / 2) + "px";
      button.appendChild(ripple);
      ripple.addEventListener("animationend", function () { ripple.remove(); });
    });
  }

  initThemeToggle();
  document.addEventListener("DOMContentLoaded", function () {
    initStagger();
    initParticles();
    initCountUp();
    initSpotlight();
    initRipple();
  });
})();
