(function () {
  "use strict";

  var SEQUENCE_TIMEOUT_MS = 1200;
  var SEARCH_DELAY_MS = 180;

  function isTyping(target) {
    if (!target) { return false; }
    var tag = target.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
  }

  function escapeHtml(text) {
    var element = document.createElement("span");
    element.textContent = text == null ? "" : String(text);
    return element.innerHTML;
  }

  function initPalette() {
    var palette = document.getElementById("command-palette");
    var help = document.getElementById("shortcut-help");
    var trigger = document.querySelector("[data-palette-open]");
    var template = document.getElementById("palette-commands");
    if (!palette || !trigger || !template) { return; }

    var input = palette.querySelector("[data-palette-input]");
    var list = palette.querySelector("[data-palette-results]");
    var searchUrl = trigger.dataset.paletteUrl;
    var commands = Array.prototype.map.call(
      template.content.querySelectorAll("[data-command]"),
      function (link) {
        return {
          label: link.textContent.trim(),
          url: link.getAttribute("href"),
          go: link.dataset.go || "",
          create: link.hasAttribute("data-create"),
          haystack: (link.textContent + " " + (link.dataset.keywords || "")).toLowerCase()
        };
      }
    );
    var entries = [];
    var activeIndex = 0;
    var searchTimer = null;
    var requestCounter = 0;
    var lastFocus = null;

    function commandUrl(predicate) {
      var match = commands.filter(predicate)[0];
      return match ? match.url : null;
    }

    function render() {
      list.innerHTML = "";
      if (!entries.length) {
        list.innerHTML = '<li class="ab-palette-empty">Keine Treffer</li>';
        return;
      }
      entries.forEach(function (entry, index) {
        var item = document.createElement("li");
        item.setAttribute("role", "option");
        item.id = "palette-option-" + index;
        item.className = "ab-palette-option" + (index === activeIndex ? " active" : "");
        item.setAttribute("aria-selected", index === activeIndex ? "true" : "false");
        if (entry.kind === "item") {
          item.innerHTML = '<span class="item-key">' + escapeHtml(entry.key) + "</span>" +
            '<span class="title">' + escapeHtml(entry.title) + "</span>" +
            '<span class="meta">' + escapeHtml(entry.project) + " · " + escapeHtml(entry.status) + "</span>";
        } else {
          item.innerHTML = '<span class="cmd-icon" aria-hidden="true">›</span>' +
            '<span class="title">' + escapeHtml(entry.label) + "</span>";
        }
        item.addEventListener("mousedown", function (event) {
          event.preventDefault();
          window.location.href = entry.url;
        });
        list.appendChild(item);
      });
      input.setAttribute("aria-activedescendant", "palette-option-" + activeIndex);
      var active = list.children[activeIndex];
      if (active && active.scrollIntoView) { active.scrollIntoView({ block: "nearest" }); }
    }

    function matchingCommands(query) {
      var words = query.toLowerCase().split(/\s+/).filter(Boolean);
      return commands.filter(function (command) {
        return words.every(function (word) { return command.haystack.indexOf(word) !== -1; });
      }).map(function (command) {
        return { kind: "command", label: command.label, url: command.url };
      });
    }

    var SKELETON_ROWS = 3;

    function appendSearchSkeleton() {
      var empty = list.querySelector(".ab-palette-empty");
      if (empty) { empty.remove(); }
      for (var index = 0; index < SKELETON_ROWS; index++) {
        var row = document.createElement("li");
        row.className = "ab-palette-skeleton";
        row.setAttribute("aria-hidden", "true");
        row.innerHTML = '<span class="ab-skeleton key"></span><span class="ab-skeleton text"></span>';
        list.appendChild(row);
      }
    }

    function update() {
      var query = input.value.trim();
      entries = matchingCommands(query);
      activeIndex = 0;
      render();
      window.clearTimeout(searchTimer);
      if (query.length < 2) { return; }
      appendSearchSkeleton();
      var requestId = ++requestCounter;
      searchTimer = window.setTimeout(function () {
        fetch(searchUrl + "?q=" + encodeURIComponent(query), {
          headers: { "Accept": "application/json", "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin"
        }).then(function (response) {
          return response.ok ? response.json() : { results: [] };
        }).then(function (data) {
          if (requestId !== requestCounter) { return; }
          var items = (data.results || []).map(function (result) {
            result.kind = "item";
            return result;
          });
          entries = items.concat(matchingCommands(query));
          activeIndex = 0;
          render();
        }).catch(function () {
          if (requestId === requestCounter) { render(); }
        });
      }, SEARCH_DELAY_MS);
    }

    function openDialog(dialog) {
      closeDialogs();
      lastFocus = document.activeElement;
      dialog.hidden = false;
      document.body.classList.add("ab-palette-open");
    }

    function closeDialogs() {
      var wasOpen = !palette.hidden || (help && !help.hidden);
      palette.hidden = true;
      if (help) { help.hidden = true; }
      document.body.classList.remove("ab-palette-open");
      if (wasOpen && lastFocus && lastFocus.focus) { lastFocus.focus(); }
    }

    function openPalette() {
      openDialog(palette);
      input.value = "";
      update();
      input.focus();
    }

    function openHelp() {
      if (!help) { return; }
      openDialog(help);
      help.setAttribute("tabindex", "-1");
      help.focus();
    }

    trigger.addEventListener("click", function (event) {
      event.preventDefault();
      openPalette();
    });
    input.addEventListener("input", update);
    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!entries.length) { return; }
        var step = event.key === "ArrowDown" ? 1 : -1;
        activeIndex = (activeIndex + step + entries.length) % entries.length;
        render();
      } else if (event.key === "Enter") {
        event.preventDefault();
        var entry = entries[activeIndex];
        if (entry) {
          window.location.href = entry.url;
        } else if (input.value.trim()) {
          window.location.href = searchUrl + "?q=" + encodeURIComponent(input.value.trim());
        }
      }
    });
    [palette, help].forEach(function (dialog) {
      if (!dialog) { return; }
      dialog.addEventListener("mousedown", function (event) {
        if (event.target === dialog) { closeDialogs(); }
      });
    });

    var pendingGo = false;
    var goTimer = null;

    document.addEventListener("keydown", function (event) {
      var dialogOpen = !palette.hidden || (help && !help.hidden);
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        if (palette.hidden) { openPalette(); } else { closeDialogs(); }
        return;
      }
      if (event.key === "Escape" && dialogOpen) {
        event.preventDefault();
        closeDialogs();
        return;
      }
      if (dialogOpen || event.ctrlKey || event.metaKey || event.altKey) { return; }
      if (isTyping(event.target) || document.querySelector(".modal.show")) { return; }

      if (pendingGo) {
        pendingGo = false;
        window.clearTimeout(goTimer);
        var url = commandUrl(function (command) { return command.go === event.key; });
        if (url) {
          event.preventDefault();
          window.location.href = url;
        }
        return;
      }
      if (event.key === "g") {
        pendingGo = true;
        goTimer = window.setTimeout(function () { pendingGo = false; }, SEQUENCE_TIMEOUT_MS);
      } else if (event.key === "/") {
        event.preventDefault();
        openPalette();
      } else if (event.key === "?") {
        event.preventDefault();
        openHelp();
      } else if (event.key === "c") {
        var createUrl = commandUrl(function (command) { return command.create; });
        event.preventDefault();
        if (createUrl) { window.location.href = createUrl; } else { openPalette(); }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", initPalette);
})();
