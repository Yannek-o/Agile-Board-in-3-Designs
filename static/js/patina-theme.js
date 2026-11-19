(function () {
  "use strict";

  var LEVEL_KEY = "ab-theme-level";
  var LEGACY_KEY = "ab-theme";
  var root = document.documentElement;
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduceMotion) { root.classList.add("motion"); }

  // Surface colours at 0 % (light) and 100 % (dark); everything in between is blended continuously.
  var LIGHT = {
    "--ab-bg": [223, 235, 237, 1],
    "--ab-bg-2": [243, 249, 249, 1],
    "--ab-surface": [255, 255, 255, 0.96],
    "--ab-surface-2": [238, 247, 248, 1],
    "--ab-surface-3": [222, 238, 240, 1],
    "--ab-card": [255, 255, 255, 1],
    "--ab-column": [255, 255, 255, 0.62],
    "--ab-input": [255, 255, 255, 1],
    "--ab-header-bg": [255, 255, 255, 0.97]
  };
  var DARK = {
    "--ab-bg": [22, 30, 31, 1],
    "--ab-bg-2": [28, 42, 43, 1],
    "--ab-surface": [46, 86, 88, 0.97],
    "--ab-surface-2": [54, 96, 98, 0.98],
    "--ab-surface-3": [66, 112, 114, 0.98],
    "--ab-card": [58, 102, 104, 0.99],
    "--ab-column": [24, 46, 48, 0.95],
    "--ab-input": [14, 32, 34, 0.9],
    "--ab-header-bg": [9, 22, 23, 0.96]
  };
  var TEXTURE = [0.1, 0.26];
  var GLASS = [[0.55, 0.35, 0.4], [0.075, 0.02, 0.04]];
  // Text colours per theme: "edge" at 0 % / 100 %, "switch" right next to the theme switch point,
  // so text gets stronger as the background approaches a mid tone.
  var TEXT = {
    light: {
      edge: { "--ab-text": [24, 54, 56, 1], "--ab-text-muted": [90, 132, 134, 1], "--ab-logo-it": [140, 140, 140, 1], "--ab-nav-text": [44, 74, 76, 1] },
      "switch": { "--ab-text": [4, 12, 13, 1], "--ab-text-muted": [22, 40, 42, 1], "--ab-logo-it": [30, 30, 30, 1], "--ab-nav-text": [6, 18, 19, 1] }
    },
    dark: {
      edge: { "--ab-text": [238, 251, 252, 1], "--ab-text-muted": [158, 194, 196, 1], "--ab-logo-it": [255, 255, 255, 1], "--ab-nav-text": [207, 227, 228, 1] },
      "switch": { "--ab-text": [255, 255, 255, 1], "--ab-text-muted": [236, 248, 248, 1], "--ab-logo-it": [255, 255, 255, 1], "--ab-nav-text": [255, 255, 255, 1] }
    }
  };
  // Relative luminance at which light and dark text have equal contrast on the cards.
  var TEXT_SWITCH_LUMINANCE = 0.233;

  function lerp(from, to, share) { return from + (to - from) * share; }

  function mixColor(from, to, share) {
    return [0, 1, 2, 3].map(function (index) { return lerp(from[index], to[index], share); });
  }

  function css(color) {
    return "rgba(" + Math.round(color[0]) + ", " + Math.round(color[1]) + ", " +
      Math.round(color[2]) + ", " + color[3].toFixed(3) + ")";
  }

  function luminance(color) {
    var channels = color.slice(0, 3).map(function (value) {
      var c = value / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  }

  function storedLevel() {
    try {
      var level = window.localStorage.getItem(LEVEL_KEY);
      if (level !== null && !isNaN(Number(level))) { return Math.min(100, Math.max(0, Number(level))); }
      return window.localStorage.getItem(LEGACY_KEY) === "light" ? 0 : 100;
    } catch (error) {
      return 100;
    }
  }

  function applyLevel(level) {
    // S-curve: fine steps near both ends, passes the mid-grey zone quickly to keep text readable.
    var centered = level / 50 - 1;
    var share = 0.5 + 0.5 * (centered < 0 ? -1 : 1) * Math.pow(Math.abs(centered), 0.6);
    Object.keys(LIGHT).forEach(function (name) {
      root.style.setProperty(name, css(mixColor(LIGHT[name], DARK[name], share)));
    });
    var glass = GLASS[0].map(function (alpha, index) { return lerp(alpha, GLASS[1][index], share).toFixed(3); });
    root.style.setProperty("--ab-glass", "linear-gradient(160deg, rgba(255, 255, 255, " + glass[0] +
      ") 0%, rgba(255, 255, 255, " + glass[1] + ") 45%, rgba(255, 255, 255, " + glass[2] + ") 100%)");
    root.style.setProperty("--ab-texture-opacity", lerp(TEXTURE[0], TEXTURE[1], share).toFixed(3));

    var card = mixColor(LIGHT["--ab-card"], DARK["--ab-card"], share);
    var cardLuminance = luminance(card);
    var theme = cardLuminance > TEXT_SWITCH_LUMINANCE ? "light" : "dark";
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-bs-theme", theme);

    // 0 at the outer end of the current theme, 1 right at the switch point.
    var lightest = luminance(LIGHT["--ab-card"]);
    var darkest = luminance(DARK["--ab-card"]);
    var closeness = theme === "light"
      ? (lightest - cardLuminance) / (lightest - TEXT_SWITCH_LUMINANCE)
      : (cardLuminance - darkest) / (TEXT_SWITCH_LUMINANCE - darkest);
    closeness = Math.min(1, Math.max(0, closeness));
    Object.keys(TEXT[theme].edge).forEach(function (name) {
      root.style.setProperty(name, css(mixColor(TEXT[theme].edge[name], TEXT[theme]["switch"][name], closeness)));
    });

    document.querySelectorAll("[data-theme-slider]").forEach(function (slider) {
      slider.value = String(level);
      slider.setAttribute("aria-valuetext", level + " % dunkel");
    });
    document.querySelectorAll("[data-theme-level]").forEach(function (label) {
      label.textContent = level + " %";
    });
  }

  // Applied before first paint so the page never flashes in the wrong theme.
  applyLevel(storedLevel());

  document.addEventListener("DOMContentLoaded", function () {
    applyLevel(storedLevel());
    document.addEventListener("input", function (event) {
      if (!event.target.matches("[data-theme-slider]")) { return; }
      var level = Number(event.target.value);
      try { window.localStorage.setItem(LEVEL_KEY, String(level)); } catch (error) { /* private mode */ }
      applyLevel(level);
    });
  });
})();
