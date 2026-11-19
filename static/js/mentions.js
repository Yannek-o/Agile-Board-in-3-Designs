/* @mention suggestions for comment fields (works inside the item dialog too). */
(function () {
  "use strict";

  var list = null;
  var state = null;

  function users(textarea) {
    return (textarea.dataset.mentionUsers || "").split(";").filter(Boolean).map(function (entry) {
      var parts = entry.split("|");
      return { username: parts[0], name: parts[1] || parts[0] };
    });
  }

  function close() {
    if (list) { list.remove(); }
    list = null;
    state = null;
  }

  function tokenBeforeCaret(textarea) {
    var before = textarea.value.slice(0, textarea.selectionStart);
    var match = /(^|\s)@([\w.+-]*)$/.exec(before);
    return match ? { query: match[2].toLowerCase(), start: textarea.selectionStart - match[2].length - 1 } : null;
  }

  function choose(index) {
    if (!state) { return; }
    var user = state.matches[index];
    var textarea = state.textarea;
    var value = textarea.value;
    var insert = "@" + user.username + " ";
    textarea.value = value.slice(0, state.start) + insert + value.slice(textarea.selectionStart);
    var caret = state.start + insert.length;
    textarea.setSelectionRange(caret, caret);
    close();
    textarea.focus();
  }

  function highlight(index) {
    state.active = (index + state.matches.length) % state.matches.length;
    list.querySelectorAll("li").forEach(function (item, position) {
      item.classList.toggle("active", position === state.active);
      item.setAttribute("aria-selected", position === state.active ? "true" : "false");
    });
  }

  function open(textarea, token) {
    var matches = users(textarea).filter(function (user) {
      return user.username.toLowerCase().indexOf(token.query) === 0 ||
        user.name.toLowerCase().indexOf(token.query) !== -1;
    }).slice(0, 6);
    if (!matches.length) { close(); return; }
    if (!list) {
      list = document.createElement("ul");
      list.className = "mention-list";
      list.setAttribute("role", "listbox");
      textarea.parentNode.insertBefore(list, textarea.nextSibling);
      list.addEventListener("mousedown", function (event) {
        var item = event.target.closest("li");
        if (item) { event.preventDefault(); choose(Number(item.dataset.index)); }
      });
    }
    state = { textarea: textarea, matches: matches, start: token.start, active: 0 };
    list.innerHTML = "";
    matches.forEach(function (user, index) {
      var item = document.createElement("li");
      item.dataset.index = String(index);
      item.setAttribute("role", "option");
      var name = document.createElement("strong");
      name.textContent = user.name;
      var handle = document.createElement("span");
      handle.textContent = "@" + user.username;
      item.appendChild(name);
      item.appendChild(handle);
      list.appendChild(item);
    });
    highlight(0);
  }

  document.addEventListener("input", function (event) {
    var textarea = event.target;
    if (!textarea.matches || !textarea.matches("textarea[data-mention-users]")) { return; }
    var token = tokenBeforeCaret(textarea);
    if (token) { open(textarea, token); } else { close(); }
  });

  document.addEventListener("keydown", function (event) {
    if (!state || event.target !== state.textarea) { return; }
    if (event.key === "ArrowDown") { event.preventDefault(); highlight(state.active + 1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); highlight(state.active - 1); }
    else if (event.key === "Enter" || event.key === "Tab") { event.preventDefault(); choose(state.active); }
    else if (event.key === "Escape") { event.preventDefault(); close(); }
  });

  document.addEventListener("focusout", function (event) {
    if (state && event.target === state.textarea) { window.setTimeout(close, 150); }
  });
})();
