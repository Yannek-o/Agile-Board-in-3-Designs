(function () {
  "use strict";

  var dragged = null;

  function updateCounts(board) {
    var singleLane = board.querySelectorAll(".board-lane").length <= 1;
    var totals = {};
    board.querySelectorAll(".board-card").forEach(function (card) {
      totals[card.dataset.status] = (totals[card.dataset.status] || 0) + 1;
    });
    board.querySelectorAll(".board-column").forEach(function (column) {
      var count = column.querySelectorAll(".board-card").length;
      var limit = parseInt(column.dataset.wipLimit, 10);
      var badge = column.querySelector(".board-count");
      if (badge) {
        badge.textContent = String(count);
        if (limit && singleLane) {
          var limitText = document.createElement("span");
          limitText.className = "board-limit";
          limitText.textContent = "/" + limit;
          badge.appendChild(limitText);
        }
      }
      column.classList.toggle(
        "over-limit", Boolean(limit) && (totals[column.dataset.status] || 0) > limit
      );
      var empty = column.querySelector(".board-empty");
      if (empty) { empty.hidden = count > 0; }
    });
  }

  function placeCard(board, card, status, version) {
    var scope = card.closest(".board-lane") || board;
    var column = scope.querySelector('.board-column[data-status="' + status + '"]');
    if (column) { column.querySelector(".board-cards").appendChild(card); }
    card.dataset.status = status;
    if (version !== undefined) {
      card.dataset.version = String(version);
      var versionInput = card.querySelector('input[name="version"]');
      if (versionInput) { versionInput.value = String(version); }
    }
    var select = card.querySelector('select[name="status"]');
    if (select) { select.value = status; }
    updateCounts(board);
  }

  function refreshBoard(board, announce) {
    return fetch(window.location.href, {
      credentials: "same-origin",
      headers: { "Accept": "text/html" },
      cache: "no-store"
    }).then(function (response) {
      if (!response.ok) { throw new Error(String(response.status)); }
      return response.text();
    }).then(function (html) {
      if (dragged) { return; }
      var doc = new DOMParser().parseFromString(html, "text/html");
      var fresh = doc.querySelector(".board");
      if (!fresh || !fresh.dataset.revision) {
        window.location.reload();
        return;
      }
      var previous = {};
      board.querySelectorAll(".board-card").forEach(function (card) {
        previous[card.dataset.item] = card.dataset.status;
      });
      board.classList.add("is-refreshed");
      board.innerHTML = fresh.innerHTML;
      board.dataset.revision = fresh.dataset.revision;
      if (announce) {
        board.querySelectorAll(".board-card").forEach(function (card) {
          if (previous[card.dataset.item] !== card.dataset.status) { card.classList.add("updated"); }
        });
      }
      var points = document.querySelector("[data-board-points]");
      var freshPoints = doc.querySelector("[data-board-points]");
      if (points && freshPoints) { points.textContent = freshPoints.textContent; }
      if (announce) {
        window.AgileBoard.showToast("Das Board wurde von einem anderen Mitarbeiter aktualisiert.", "info");
      }
    }).catch(function () { /* the next poll retries */ });
  }

  function initDragAndDrop(board) {
    var moveUrl = board.dataset.moveUrl;
    var effects = window.BoardEffects || null;

    function clearHighlight() {
      board.querySelectorAll(".drag-over").forEach(function (column) {
        column.classList.remove("drag-over");
      });
    }

    if (effects) {
      document.addEventListener("dragover", function (event) {
        if (dragged) { effects.trail(event.clientX, event.clientY); }
      });
    }

    board.addEventListener("dragstart", function (event) {
      var card = event.target.closest(".board-card[draggable='true']");
      if (!card) { return; }
      dragged = card;
      card.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.dataset.item);
    });

    board.addEventListener("dragend", function () {
      if (dragged) { dragged.classList.remove("dragging"); }
      if (effects) { effects.endTrail(); }
      clearHighlight();
      dragged = null;
    });

    board.addEventListener("dragover", function (event) {
      var column = event.target.closest(".board-column");
      if (!dragged || !column) { return; }
      event.preventDefault();
      if (!column.classList.contains("drag-over")) {
        clearHighlight();
        column.classList.add("drag-over");
      }
    });

    function statusLabel(card, status) {
      var option = card.querySelector('select[name="status"] option[value="' + status + '"]');
      return option ? option.textContent.trim() : status;
    }

    function moveCard(card, newStatus, offerUndo) {
      var previousStatus = card.dataset.status;
      if (previousStatus === newStatus) { return; }
      placeCard(board, card, newStatus);
      window.AgileBoard.postJson(moveUrl, {
        item: Number(card.dataset.item),
        status: newStatus,
        version: Number(card.dataset.version)
      }).then(function (result) {
        if (result.ok) {
          placeCard(board, card, result.body.status, result.body.version);
          card.classList.remove("landed");
          void card.offsetWidth;
          card.classList.add("landed");
          if (result.body.revision) { board.dataset.revision = result.body.revision; }
          if (offerUndo) {
            window.AgileBoard.showToast(
              result.body.key + " → " + statusLabel(card, result.body.status), "success",
              {
                actionLabel: "Rückgängig",
                onAction: function () {
                  var current = board.querySelector('.board-card[data-item="' + card.dataset.item + '"]');
                  if (current) { moveCard(current, previousStatus, false); }
                }
              }
            );
          }
          window.setTimeout(function () { refreshBoard(board, false); }, 700);
        } else if (result.status === 409) {
          placeCard(board, card, result.body.status, result.body.version);
          window.AgileBoard.showToast(result.body.error, "danger");
          refreshBoard(board, false);
        } else {
          placeCard(board, card, previousStatus);
          window.AgileBoard.showToast(
            (result.body && result.body.error) || "Die Änderung konnte nicht gespeichert werden.",
            "danger"
          );
        }
      }).catch(function () {
        placeCard(board, card, previousStatus);
        window.AgileBoard.showToast("Netzwerkfehler – bitte erneut versuchen.", "danger");
      });
    }

    board.addEventListener("drop", function (event) {
      var column = event.target.closest(".board-column");
      if (!dragged || !column) { return; }
      event.preventDefault();
      clearHighlight();
      moveCard(dragged, column.dataset.status, true);
    });
  }

  function initLiveUpdates(board) {
    var interval = Number(board.dataset.pollInterval) || 10000;
    var busy = false;

    function poll() {
      if (busy || dragged || document.hidden) { return; }
      busy = true;
      fetch(board.dataset.stateUrl, {
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        cache: "no-store"
      }).then(function (response) {
        return response.ok ? response.json() : null;
      }).then(function (state) {
        if (state && state.revision !== board.dataset.revision) {
          return refreshBoard(board, true);
        }
      }).catch(function () { /* offline: retry on the next interval */ })
        .then(function () { busy = false; });
    }

    window.setInterval(poll, interval);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) { poll(); }
    });
  }

  function initQuickCreate(board) {
    board.addEventListener("submit", function (event) {
      var form = event.target.closest("form[data-quick-create]");
      if (!form) { return; }
      event.preventDefault();
      var input = form.querySelector('input[name="title"]');
      var title = input.value.trim();
      if (!title) { return; }
      var status = form.querySelector('input[name="status"]').value;
      var itemType = form.querySelector('select[name="item_type"]').value;
      input.disabled = true;
      window.AgileBoard.postJson(form.action, {
        title: title, status: status, item_type: itemType
      }).then(function (result) {
        if (!result.ok) {
          input.disabled = false;
          window.AgileBoard.showToast((result.body && result.body.error) || "Die Karte konnte nicht angelegt werden.", "danger");
          return;
        }
        if (result.body.revision) { board.dataset.revision = result.body.revision; }
        return refreshBoard(board, false).then(function () {
          var fresh = board.querySelector('form[data-quick-create] input[name="status"][value="' + status + '"]');
          var freshInput = fresh && fresh.form.querySelector('input[name="title"]');
          if (freshInput) {
            freshInput.form.querySelector('select[name="item_type"]').value = itemType;
            freshInput.focus();
          }
          var card = board.querySelector('.board-card[data-item="' + result.body.item + '"]');
          if (card) { card.classList.add("landed"); }
        });
      }).catch(function () {
        input.disabled = false;
        window.AgileBoard.showToast("Netzwerkfehler – bitte erneut versuchen.", "danger");
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".board[data-move-url]").forEach(initDragAndDrop);
    document.querySelectorAll(".board[data-state-url]").forEach(initLiveUpdates);
    document.querySelectorAll(".board").forEach(initQuickCreate);
    document.addEventListener("ab:itemchanged", function () {
      document.querySelectorAll(".board[data-state-url]").forEach(function (board) {
        refreshBoard(board, false);
      });
    });
  });
})();
