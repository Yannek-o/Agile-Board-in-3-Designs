(function () {
  "use strict";

  function csrfToken(form) {
    var field = form.querySelector("input[name=csrfmiddlewaretoken]");
    return field ? field.value : "";
  }

  function escapeHtml(text) {
    var element = document.createElement("span");
    element.textContent = text == null ? "" : String(text);
    return element.innerHTML;
  }

  function initPoker(root) {
    var stateUrl = root.dataset.stateUrl;
    var interval = Number(root.dataset.poll || 2000);
    var seats = root.querySelector("[data-poker-votes]");
    var summary = root.querySelector("[data-poker-summary]");
    var statusBadge = root.querySelector("[data-poker-status]");
    var roundLabel = root.querySelector("[data-poker-round]");
    var deck = root.querySelector("[data-poker-deck]");
    var points = root.querySelector("[data-poker-points]");
    var revealButton = root.querySelector("[data-show-when=voting]");
    var lastStatus = null;
    var timer = null;

    function render(state) {
      if (state.status === "closed") {
        window.location.reload();
        return;
      }
      statusBadge.textContent = state.status_label;
      roundLabel.textContent = state.round;
      seats.innerHTML = state.votes.map(function (vote) {
        var face = vote.value ? escapeHtml(vote.value) : (vote.voted ? "✓" : "…");
        return '<li class="poker-seat' + (vote.voted ? " voted" : "") +
          (vote.value ? " revealed" : "") + '">' +
          '<span class="poker-card-back">' + face + "</span>" +
          '<span class="small">' + escapeHtml(vote.name) + "</span></li>";
      }).join("");
      if (state.summary) {
        summary.hidden = false;
        summary.innerHTML = "Ø " + state.summary.average + " · Min " + state.summary.min +
          " · Max " + state.summary.max + " · Vorschlag <strong>" + state.summary.suggestion +
          "</strong>" + (state.summary.consensus ? " · Einigkeit 🎉" : "");
        if (points && lastStatus !== state.status) { points.value = state.summary.suggestion; }
      } else {
        summary.hidden = true;
      }
      if (deck) {
        deck.querySelectorAll("button[name=value]").forEach(function (button) {
          var selected = button.value === state.my_vote;
          button.classList.toggle("selected", selected);
          button.setAttribute("aria-pressed", selected ? "true" : "false");
          button.disabled = state.status !== "voting";
        });
      }
      if (revealButton) { revealButton.hidden = state.status !== "voting"; }
      lastStatus = state.status;
    }

    function refresh() {
      return fetch(stateUrl, {
        headers: { "Accept": "application/json" }, credentials: "same-origin"
      }).then(function (response) {
        return response.ok ? response.json() : null;
      }).then(function (state) {
        if (state) { render(state); }
      }).catch(function () { /* next poll retries */ });
    }

    function post(form, extra) {
      var data = new FormData(form);
      if (extra) { data.append(extra.name, extra.value); }
      return fetch(form.action, {
        method: "POST",
        body: data,
        headers: { "Accept": "application/json", "X-CSRFToken": csrfToken(form) },
        credentials: "same-origin"
      }).then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            if (window.AgileBoard && window.AgileBoard.showToast) {
              window.AgileBoard.showToast(body.error || "Aktion fehlgeschlagen.", "danger");
            }
            return;
          }
          render(body);
        });
      });
    }

    if (deck) {
      deck.addEventListener("submit", function (event) {
        event.preventDefault();
        var button = event.submitter;
        if (button) { post(deck, { name: "value", value: button.value }); }
      });
    }
    root.querySelectorAll("[data-poker-action]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        post(form);
      });
    });

    function schedule() {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        if (document.hidden) { schedule(); return; }
        refresh().then(schedule);
      }, interval);
    }
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) { refresh(); }
    });
    refresh().then(schedule);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-poker]");
    if (root) { initPoker(root); }
  });
})();
