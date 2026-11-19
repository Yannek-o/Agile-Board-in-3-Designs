/* In-place editing of item fields on the detail page and in the item dialog. */
(function () {
  "use strict";

  var editing = null;

  function safeMatches(element, selector) {
    try { return element.matches(selector); } catch (error) { return false; }
  }

  function panelOf(element) { return element.closest("[data-inline-url]"); }

  function buildControl(field) {
    var type = field.dataset.inlineType;
    var control;
    if (type === "textarea") {
      control = document.createElement("textarea");
      control.rows = 6;
    } else if (type === "select") {
      control = document.createElement("select");
      control.className = "form-select form-select-sm";
      var template = field.querySelector("template");
      if (template) { control.appendChild(template.content.cloneNode(true)); }
    } else {
      control = document.createElement("input");
      control.type = type === "number" ? "number" : (type === "date" ? "date" : "text");
      if (type === "number") { control.min = "0"; control.max = "100"; }
    }
    if (type !== "select") { control.className = "form-control form-control-sm"; }
    control.classList.add("inline-control");
    control.value = field.dataset.value || "";
    control.setAttribute("aria-label", field.getAttribute("aria-label") || "Wert");
    return control;
  }

  function finish(field) {
    var control = field.querySelector(".inline-control");
    if (control) { control.remove(); }
    field.querySelector(".inline-display").hidden = false;
    field.classList.remove("is-editing");
    editing = null;
  }

  function updateVersion(panel, version) {
    panel.dataset.version = String(version);
    panel.querySelectorAll('input[name="version"]').forEach(function (input) {
      input.value = String(version);
    });
  }

  function save(field, control) {
    var panel = panelOf(field);
    var value = control.value;
    if (value === (field.dataset.value || "")) { finish(field); return; }
    control.disabled = true;
    window.AgileBoard.postJson(panel.dataset.inlineUrl, {
      field: field.dataset.inlineField,
      value: value,
      version: Number(panel.dataset.version)
    }).then(function (result) {
      var body = result.body || {};
      if (result.ok || result.status === 409) {
        field.dataset.value = body.value;
        var display = field.querySelector(".inline-display");
        if (typeof body.html === "string") {
          display.innerHTML = body.html;
        } else {
          display.textContent = body.display;
        }
        updateVersion(panel, body.version);
        finish(field);
        if (result.ok) {
          field.classList.add("inline-saved");
          window.setTimeout(function () { field.classList.remove("inline-saved"); }, 1200);
          document.dispatchEvent(new CustomEvent("ab:itemchanged"));
        } else {
          window.AgileBoard.showToast(body.error + " Der aktuelle Stand wird angezeigt.", "danger");
        }
        return;
      }
      control.disabled = false;
      control.focus();
      window.AgileBoard.showToast(body.error || "Die Änderung konnte nicht gespeichert werden.", "danger");
    }).catch(function () {
      control.disabled = false;
      window.AgileBoard.showToast("Netzwerkfehler – bitte erneut versuchen.", "danger");
    });
  }

  function start(field) {
    if (editing === field) { return; }
    if (editing) { finish(editing); }
    editing = field;
    var control = buildControl(field);
    field.classList.add("is-editing");
    field.querySelector(".inline-display").hidden = true;
    field.appendChild(control);
    control.focus();
    if (control.select && control.type === "text") { control.select(); }

    control.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        finish(field);
        field.focus();
      } else if (event.key === "Enter" && (control.tagName !== "TEXTAREA" || event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        save(field, control);
      }
    });
    control.addEventListener("focusout", function (event) {
      if (control.contains(event.relatedTarget)) { return; }
      if (control.matches && safeMatches(control, ":open")) { return; }
      if (editing === field && !control.disabled) { save(field, control); }
    });
    if (control.tagName === "SELECT") {
      control.addEventListener("change", function () { save(field, control); });
    }
  }

  document.addEventListener("click", function (event) {
    var field = event.target.closest("[data-inline-field]");
    if (!field || event.target.closest(".inline-control") || event.target.closest("a")) { return; }
    start(field);
  });

  document.addEventListener("keydown", function (event) {
    var field = event.target.closest && event.target.closest("[data-inline-field]");
    if (!field || event.target !== field) { return; }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      start(field);
    }
  });
})();
