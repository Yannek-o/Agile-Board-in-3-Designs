(function () {
  "use strict";

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  function postJson(url, payload) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-CSRFToken": csrfToken()
      },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        return { status: response.status, ok: response.ok, body: body };
      });
    });
  }

  var TOAST_DURATION_MS = { success: 6000, info: 6000, warning: 10000, danger: 10000 };

  function postAndNavigate(url) {
    var form = document.createElement("form");
    form.method = "post";
    form.action = url;
    var token = document.createElement("input");
    token.type = "hidden";
    token.name = "csrfmiddlewaretoken";
    token.value = csrfToken();
    form.appendChild(token);
    document.body.appendChild(form);
    form.submit();
  }

  function dismissToast(toast) {
    if (toast.classList.contains("is-leaving")) { return; }
    toast.classList.add("is-leaving");
    window.setTimeout(function () { toast.remove(); }, 260);
  }

  // Auto-hide pauses while the pointer or focus is inside the toast.
  function activateToast(toast) {
    var kind = toast.dataset.kind || "info";
    var remaining = TOAST_DURATION_MS[kind] || TOAST_DURATION_MS.info;
    var startedAt = 0;
    var timer = null;
    var hovered = false;
    var focused = false;

    function start() {
      startedAt = Date.now();
      toast.classList.remove("is-paused");
      timer = window.setTimeout(function () { dismissToast(toast); }, remaining);
    }

    function pause() {
      if (timer === null) { return; }
      window.clearTimeout(timer);
      timer = null;
      remaining -= Date.now() - startedAt;
      toast.classList.add("is-paused");
    }

    function resumeIfIdle() {
      if (!hovered && !focused && timer === null) { start(); }
    }

    toast.style.setProperty("--toast-duration", remaining + "ms");
    toast.classList.add("is-timed");
    toast.addEventListener("mouseenter", function () { hovered = true; pause(); });
    toast.addEventListener("mouseleave", function () { hovered = false; resumeIfIdle(); });
    toast.addEventListener("focusin", function () { focused = true; pause(); });
    toast.addEventListener("focusout", function () { focused = false; resumeIfIdle(); });
    var close = toast.querySelector("[data-toast-close]");
    if (close) { close.addEventListener("click", function () { dismissToast(toast); }); }
    start();
  }

  /*
   * options.actionLabel + options.onAction add a button (e.g. "Rückgängig");
   * options.undoUrl posts to that URL instead of calling a function.
   */
  function showToast(message, kind, options) {
    var container = document.getElementById("ab-live-messages");
    if (!container) { return null; }
    options = options || {};
    kind = kind || "info";
    var toast = document.createElement("div");
    toast.className = "ab-toast toast-" + kind;
    toast.dataset.kind = kind;
    if (kind === "danger") { toast.setAttribute("role", "alert"); }
    var icon = document.createElement("span");
    icon.className = "ab-toast-icon";
    icon.setAttribute("aria-hidden", "true");
    var text = document.createElement("span");
    text.className = "ab-toast-text";
    text.textContent = message;
    toast.appendChild(icon);
    toast.appendChild(text);
    var onAction = options.onAction || (options.undoUrl ? function () { postAndNavigate(options.undoUrl); } : null);
    if (onAction) {
      var action = document.createElement("button");
      action.type = "button";
      action.className = "ab-toast-action";
      action.textContent = options.actionLabel || "Rückgängig";
      action.addEventListener("click", function () {
        action.disabled = true;
        dismissToast(toast);
        onAction();
      });
      toast.appendChild(action);
    }
    var close = document.createElement("button");
    close.type = "button";
    close.className = "ab-toast-close";
    close.setAttribute("data-toast-close", "");
    close.setAttribute("aria-label", "Schließen");
    close.textContent = "×";
    toast.appendChild(close);
    container.appendChild(toast);
    activateToast(toast);
    return toast;
  }

  function showServerMessages(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    doc.querySelectorAll("#ab-live-messages .ab-toast").forEach(function (toast) {
      var text = toast.querySelector(".ab-toast-text");
      showToast(text ? text.textContent.trim() : "", toast.dataset.kind, {
        undoUrl: toast.dataset.undoUrl || null
      });
    });
  }

  function initServerToasts() {
    document.querySelectorAll("#ab-live-messages .ab-toast").forEach(activateToast);
  }

  var ITEM_SKELETON =
    '<div class="ab-skeleton-panel" aria-busy="true">' +
      '<span class="visually-hidden">Wird geladen …</span>' +
      '<div class="stack" aria-hidden="true">' +
        '<span class="ab-skeleton title"></span>' +
        '<div class="chips"><span class="ab-skeleton chip"></span><span class="ab-skeleton chip"></span><span class="ab-skeleton chip"></span></div>' +
        '<span class="ab-skeleton" style="width: 100%"></span>' +
        '<span class="ab-skeleton" style="width: 94%"></span>' +
        '<span class="ab-skeleton" style="width: 86%"></span>' +
        '<span class="ab-skeleton" style="width: 58%"></span>' +
        '<span class="ab-skeleton block"></span>' +
      '</div>' +
      '<div class="stack" aria-hidden="true">' +
        '<span class="ab-skeleton" style="width: 40%"></span><span class="ab-skeleton field"></span>' +
        '<span class="ab-skeleton" style="width: 50%"></span><span class="ab-skeleton field"></span>' +
        '<span class="ab-skeleton" style="width: 35%"></span><span class="ab-skeleton field"></span>' +
        '<span class="ab-skeleton" style="width: 45%"></span><span class="ab-skeleton field"></span>' +
      '</div>' +
    '</div>';

  function initItemModal() {
    var modalElement = document.getElementById("itemModal");
    if (!modalElement || !window.bootstrap) { return; }
    var modal = new window.bootstrap.Modal(modalElement);
    var body = modalElement.querySelector(".modal-body");
    var title = modalElement.querySelector(".modal-title");
    var panelUrl = null;
    var itemUrl = null;

    function loadPanel() {
      return fetch(panelUrl, { credentials: "same-origin", cache: "no-store" })
        .then(function (response) {
          if (!response.ok) { throw new Error(String(response.status)); }
          return response.text();
        })
        .then(function (html) { body.innerHTML = html; })
        .catch(function () { window.location.href = itemUrl; });
    }

    document.addEventListener("click", function (event) {
      var link = event.target.closest("a[data-item-modal]");
      if (!link || event.ctrlKey || event.metaKey || event.shiftKey) { return; }
      event.preventDefault();
      var url = new URL(link.href, window.location.origin);
      url.searchParams.set("partial", "1");
      url.searchParams.set("next", window.location.pathname + window.location.search);
      panelUrl = url.toString();
      itemUrl = link.href;
      body.innerHTML = ITEM_SKELETON;
      title.textContent = link.getAttribute("data-item-key") || "Details";
      modal.show();
      loadPanel();
    });

    // Forms inside the dialog are sent in the background so the dialog stays open.
    body.addEventListener("submit", function (event) {
      var form = event.target;
      if (event.defaultPrevented || !panelUrl || form.method.toLowerCase() !== "post") { return; }
      event.preventDefault();
      var buttons = form.querySelectorAll("button, input[type=submit]");
      buttons.forEach(function (button) { button.disabled = true; });
      var data = new FormData(form);
      if (event.submitter && event.submitter.name) {
        data.append(event.submitter.name, event.submitter.value);
      }
      fetch(form.action, { method: "POST", credentials: "same-origin", body: data })
        .then(function (response) {
          if (!response.ok) { throw new Error(String(response.status)); }
          return response.text();
        })
        .then(function (html) {
          showServerMessages(html);
          document.dispatchEvent(new CustomEvent("ab:itemchanged"));
          return loadPanel();
        })
        .catch(function () {
          buttons.forEach(function (button) { button.disabled = false; });
          showToast("Die Änderung konnte nicht gespeichert werden.", "danger");
        });
    });
  }

  function initBackButton() {
    var header = document.querySelector(".ab-page-header");
    if (!header || window.location.pathname === "/") { return; }
    var actions = header.querySelector(".actions");
    if (!actions) {
      actions = document.createElement("div");
      actions.className = "actions";
      header.appendChild(actions);
    }
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-ghost btn-back";
    button.innerHTML = '<span aria-hidden="true">←</span> Zurück';
    button.addEventListener("click", function () {
      var cameFromApp = document.referrer && new URL(document.referrer).origin === window.location.origin;
      if (cameFromApp && window.history.length > 1) {
        window.history.back();
      } else {
        window.location.href = "/";
      }
    });
    actions.insertBefore(button, actions.firstChild);
  }

  function initDashboardNotes() {
    var form = document.querySelector("[data-dashboard-notes]");
    if (!form) { return; }
    var field = form.querySelector("textarea");
    var status = form.querySelector("[data-notes-status]");
    var timer = null;
    var lastSaved = field.value;

    function save() {
      if (field.value === lastSaved) { return; }
      var value = field.value;
      status.textContent = "Speichert …";
      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
        credentials: "same-origin"
      }).then(function (response) {
        if (!response.ok) { throw new Error(); }
        lastSaved = value;
        status.textContent = "Gespeichert";
      }).catch(function () {
        status.textContent = "Nicht gespeichert";
      });
    }

    field.addEventListener("input", function () {
      clearTimeout(timer);
      status.textContent = "";
      timer = setTimeout(save, 800);
    });
    field.addEventListener("blur", function () { clearTimeout(timer); save(); });
    form.addEventListener("submit", function (event) { event.preventDefault(); save(); });
  }

  window.AgileBoard = { postJson: postJson, showToast: showToast };
  document.addEventListener("DOMContentLoaded", initServerToasts);
  document.addEventListener("DOMContentLoaded", initDashboardNotes);
  document.addEventListener("DOMContentLoaded", initItemModal);
  document.addEventListener("DOMContentLoaded", initBackButton);
})();
