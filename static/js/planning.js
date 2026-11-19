/* Backlog planning: drag items between sprint sections and the backlog. */
(function () {
  "use strict";

  function refreshSection(zone) {
    var section = zone.closest(".plan-section");
    var rows = zone.querySelectorAll(".plan-row");
    var points = 0;
    rows.forEach(function (row) { points += Number(row.dataset.points || 0); });
    section.querySelector("[data-section-count]").textContent = String(rows.length);
    section.querySelector("[data-section-points]").textContent = String(points);
    var empty = zone.querySelector(".plan-empty");
    if (empty) { empty.hidden = rows.length > 0; }
  }

  function syncSelect(row, sprint) {
    var select = row.querySelector('select[name="sprint"]');
    if (select) { select.value = sprint || "backlog"; }
  }

  function init(board) {
    var moveUrl = board.dataset.moveUrl;
    var dragged = null;

    function clearHighlight() {
      board.querySelectorAll(".drag-over").forEach(function (zone) { zone.classList.remove("drag-over"); });
    }

    board.addEventListener("dragstart", function (event) {
      var row = event.target.closest(".plan-row[draggable='true']");
      if (!row) { return; }
      dragged = row;
      row.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", row.dataset.item);
    });

    board.addEventListener("dragend", function () {
      if (dragged) { dragged.classList.remove("dragging"); }
      clearHighlight();
      dragged = null;
    });

    board.addEventListener("dragover", function (event) {
      var zone = event.target.closest(".plan-dropzone");
      if (!dragged || !zone) { return; }
      event.preventDefault();
      if (!zone.classList.contains("drag-over")) {
        clearHighlight();
        zone.classList.add("drag-over");
      }
    });

    board.addEventListener("drop", function (event) {
      var zone = event.target.closest(".plan-dropzone");
      if (!dragged || !zone) { return; }
      event.preventDefault();
      clearHighlight();
      var row = dragged;
      var source = row.closest(".plan-dropzone");
      if (source === zone) { return; }
      var sprint = zone.dataset.sprint;
      zone.insertBefore(row, zone.querySelector(".plan-empty"));
      refreshSection(zone);
      refreshSection(source);
      window.AgileBoard.postJson(moveUrl, {
        item: Number(row.dataset.item),
        sprint: sprint ? Number(sprint) : null
      }).then(function (result) {
        if (result.ok) {
          syncSelect(row, sprint);
          row.classList.remove("landed");
          void row.offsetWidth;
          row.classList.add("landed");
          return;
        }
        source.insertBefore(row, source.querySelector(".plan-empty"));
        refreshSection(zone);
        refreshSection(source);
        window.AgileBoard.showToast(
          (result.body && result.body.error) || "Die Änderung konnte nicht gespeichert werden.",
          "danger"
        );
      }).catch(function () {
        source.insertBefore(row, source.querySelector(".plan-empty"));
        refreshSection(zone);
        refreshSection(source);
        window.AgileBoard.showToast("Netzwerkfehler – bitte erneut versuchen.", "danger");
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".plan-board[data-move-url]").forEach(init);
  });
})();
