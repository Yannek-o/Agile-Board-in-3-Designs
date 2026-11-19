/* Avatar colour picker in the user menu: live preview, autosave, presets. */
(function () {
  "use strict";

  function initAvatarColor() {
    var form = document.querySelector("[data-avatar-color]");
    var toggle = document.querySelector("[data-avatar-color-toggle]");
    if (!form || !toggle) { return; }
    var color = form.querySelector('input[name="color"]');
    var color2 = form.querySelector('input[name="color_2"]');
    var gradient = form.querySelector('input[name="gradient"]');
    var gradientField = form.querySelector("[data-gradient-field]");
    var status = form.querySelector("[data-avatar-status]");
    var timer = null;

    toggle.addEventListener("click", function () {
      var open = form.hidden;
      form.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
    });

    function background() {
      return gradient.checked
        ? "linear-gradient(135deg, " + color.value + " 0%, " + color2.value + " 100%)"
        : color.value;
    }

    function luminance(hex) {
      var channels = [1, 3, 5].map(function (index) {
        var value = parseInt(hex.substr(index, 2), 16) / 255;
        return value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
    }

    function textColor() {
      var colors = gradient.checked ? [color.value, color2.value] : [color.value];
      var average = colors.reduce(function (sum, hex) { return sum + luminance(hex); }, 0) / colors.length;
      return average > 0.179 ? "#1a1a1a" : "#ffffff";
    }

    function paint(bg, fg) {
      document.querySelectorAll(".avatar.me, .avatar-color-dot").forEach(function (avatar) {
        if (bg) {
          avatar.classList.add("has-color");
          avatar.style.setProperty("--avatar-bg", bg);
          avatar.style.setProperty("--avatar-fg", fg);
        } else {
          avatar.classList.remove("has-color");
          avatar.style.removeProperty("--avatar-bg");
          avatar.style.removeProperty("--avatar-fg");
        }
      });
    }

    function send(reset) {
      var data = new FormData(form);
      if (reset) { data.set("reset", "1"); }
      status.textContent = "Speichert …";
      return fetch(form.action, {
        method: "POST",
        body: data,
        headers: { Accept: "application/json" },
        credentials: "same-origin"
      }).then(function (response) {
        return response.json().then(function (payload) {
          if (!response.ok) { throw new Error(payload.error || ""); }
          paint(payload.background, payload.text);
          status.textContent = reset ? "Zurückgesetzt" : "Gespeichert";
        });
      }).catch(function (error) {
        status.textContent = error.message || "Nicht gespeichert";
      });
    }

    function preview() {
      gradientField.hidden = !gradient.checked;
      paint(background(), textColor());
      clearTimeout(timer);
      status.textContent = "";
      timer = setTimeout(function () { send(false); }, 600);
    }

    [color, color2, gradient].forEach(function (input) {
      input.addEventListener("input", preview);
      input.addEventListener("change", preview);
    });

    form.querySelectorAll(".avatar-preset").forEach(function (button) {
      button.addEventListener("click", function () {
        var second = button.getAttribute("data-color-2");
        color.value = button.getAttribute("data-color");
        if (second) { color2.value = second; }
        gradient.checked = Boolean(second);
        preview();
      });
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      clearTimeout(timer);
      var reset = event.submitter && event.submitter.hasAttribute("data-avatar-reset");
      send(reset);
    });
  }

  document.addEventListener("DOMContentLoaded", initAvatarColor);
})();
