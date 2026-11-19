(function () {
  "use strict";

  function initReorder(table) {
    var body = table.querySelector("tbody");
    var reorderUrl = table.dataset.reorderUrl;
    var dragged = null;

    body.addEventListener("dragstart", function (event) {
      var row = event.target.closest("tr[data-item]");
      if (!row) { return; }
      dragged = row;
      row.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", row.dataset.item);
    });

    body.addEventListener("dragover", function (event) {
      var row = event.target.closest("tr[data-item]");
      if (!dragged || !row || row === dragged) { return; }
      event.preventDefault();
      body.querySelectorAll(".drop-target").forEach(function (entry) {
        entry.classList.remove("drop-target");
      });
      row.classList.add("drop-target");
    });

    body.addEventListener("drop", function (event) {
      var target = event.target.closest("tr[data-item]");
      if (!dragged || !target || target === dragged) { return; }
      event.preventDefault();
      target.classList.remove("drop-target");
      var rows = Array.prototype.slice.call(body.querySelectorAll("tr[data-item]"));
      var fromIndex = rows.indexOf(dragged);
      var toIndex = rows.indexOf(target);
      if (fromIndex < toIndex) {
        target.after(dragged);
      } else {
        target.before(dragged);
      }
      var offset = Number(table.dataset.offset || 0);
      window.AgileBoard.postJson(reorderUrl, {
        item: Number(dragged.dataset.item),
        position: offset + toIndex
      }).then(function (result) {
        if (!result.ok) {
          window.AgileBoard.showToast("Reihenfolge konnte nicht gespeichert werden.", "danger");
          window.setTimeout(function () { window.location.reload(); }, 1200);
        }
      });
    });

    body.addEventListener("dragend", function () {
      if (dragged) { dragged.classList.remove("dragging"); }
      body.querySelectorAll(".drop-target").forEach(function (entry) {
        entry.classList.remove("drop-target");
      });
      dragged = null;
    });
  }

  function initBulk(form) {
    var items = Array.prototype.slice.call(document.querySelectorAll("[data-bulk-item]"));
    var all = document.querySelector("[data-bulk-all]");
    var count = form.querySelector("[data-bulk-count]");
    var action = form.querySelector("[data-bulk-action]");
    var value = form.querySelector("[data-bulk-value]");

    function syncValues() {
      var first = null;
      value.querySelectorAll("option").forEach(function (option) {
        var visible = option.dataset.for === action.value;
        option.hidden = !visible;
        option.disabled = !visible;
        if (visible && !first) { first = option; }
      });
      value.hidden = action.value === "archive";
      if (first) { value.value = first.value; }
    }

    function syncSelection() {
      var selected = items.filter(function (box) { return box.checked; }).length;
      form.hidden = selected === 0;
      count.textContent = selected + " ausgewählt";
      if (all) {
        all.checked = selected > 0 && selected === items.length;
        all.indeterminate = selected > 0 && selected < items.length;
      }
      items.forEach(function (box) {
        box.closest("tr").classList.toggle("is-selected", box.checked);
      });
    }

    items.forEach(function (box) { box.addEventListener("change", syncSelection); });
    if (all) {
      all.addEventListener("change", function () {
        items.forEach(function (box) { box.checked = all.checked; });
        syncSelection();
      });
    }
    form.querySelector("[data-bulk-clear]").addEventListener("click", function () {
      items.forEach(function (box) { box.checked = false; });
      syncSelection();
    });
    action.addEventListener("change", syncValues);
    form.addEventListener("submit", function (event) {
      if (action.value === "archive" && !window.confirm("Ausgewählte Einträge archivieren?")) {
        event.preventDefault();
      }
    });
    syncValues();
    syncSelection();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("table[data-reorder-url]").forEach(initReorder);
    var bulkForm = document.querySelector("[data-bulk-form]");
    if (bulkForm) { initBulk(bulkForm); }
  });
})();
