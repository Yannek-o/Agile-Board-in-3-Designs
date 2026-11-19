(function () {
  "use strict";

  function formatSize(bytes) {
    if (bytes < 1024) { return bytes + " B"; }
    if (bytes < 1024 * 1024) { return Math.round(bytes / 1024) + " KB"; }
    return (bytes / (1024 * 1024)).toFixed(1).replace(".", ",") + " MB";
  }

  function screenshotName(type) {
    var now = new Date();
    var pad = function (value) { return String(value).padStart(2, "0"); };
    var stamp = now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate()) +
      "_" + pad(now.getHours()) + pad(now.getMinutes()) + pad(now.getSeconds());
    var extension = (type.split("/")[1] || "png").replace("jpeg", "jpg");
    return "screenshot_" + stamp + "." + extension;
  }

  function initAttachments(side) {
    var input = side.querySelector('input[type="file"]');
    var dropzone = side.querySelector("[data-dropzone]");
    var list = side.querySelector("[data-upload-list]");
    var errors = side.querySelector("[data-upload-errors]");
    var maxBytes = parseInt(side.dataset.maxBytes, 10) || Infinity;
    var allowed = side.dataset.accept.split(",").map(function (ext) { return ext.trim().toLowerCase(); });
    var selected = [];

    function showError(message) {
      var entry = document.createElement("li");
      entry.textContent = message;
      errors.appendChild(entry);
    }

    function syncInput() {
      var transfer = new DataTransfer();
      selected.forEach(function (file) { transfer.items.add(file); });
      input.files = transfer.files;
    }

    function render() {
      list.innerHTML = "";
      selected.forEach(function (file, index) {
        var row = document.createElement("li");
        row.className = "upload-item";
        var preview = document.createElement("span");
        preview.className = "upload-preview";
        if (file.type.indexOf("image/") === 0) {
          var image = document.createElement("img");
          image.alt = "";
          image.src = URL.createObjectURL(file);
          image.onload = function () { URL.revokeObjectURL(image.src); };
          preview.appendChild(image);
        } else {
          preview.textContent = file.name.split(".").pop().toUpperCase();
        }
        var name = document.createElement("span");
        name.className = "upload-name";
        name.textContent = file.name;
        var size = document.createElement("small");
        size.textContent = formatSize(file.size);
        name.appendChild(size);
        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "btn btn-sm btn-metal-danger";
        remove.setAttribute("aria-label", file.name + " entfernen");
        remove.textContent = "×";
        remove.addEventListener("click", function () {
          selected.splice(index, 1);
          syncInput();
          render();
        });
        row.append(preview, name, remove);
        list.appendChild(row);
      });
    }

    function addFiles(files) {
      errors.innerHTML = "";
      Array.prototype.forEach.call(files, function (file) {
        var extension = "." + file.name.split(".").pop().toLowerCase();
        if (allowed.indexOf(extension) === -1) {
          showError(file.name + ": Dateityp nicht erlaubt.");
        } else if (file.size > maxBytes) {
          showError(file.name + ": Datei ist größer als " + formatSize(maxBytes) + ".");
        } else {
          selected.push(file);
        }
      });
      syncInput();
      render();
    }

    input.addEventListener("change", function () {
      var picked = Array.prototype.slice.call(input.files);
      addFiles(picked);
    });

    ["dragenter", "dragover"].forEach(function (type) {
      dropzone.addEventListener(type, function (event) {
        event.preventDefault();
        dropzone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (type) {
      dropzone.addEventListener(type, function () { dropzone.classList.remove("is-dragover"); });
    });
    dropzone.addEventListener("drop", function (event) {
      event.preventDefault();
      addFiles(event.dataTransfer.files);
    });

    document.addEventListener("paste", function (event) {
      var items = (event.clipboardData && event.clipboardData.items) || [];
      var pasted = [];
      Array.prototype.forEach.call(items, function (item) {
        var file = item.kind === "file" ? item.getAsFile() : null;
        if (!file) { return; }
        if (file.type.indexOf("image/") === 0 && (!file.name || file.name === "image.png")) {
          file = new File([file], screenshotName(file.type), { type: file.type });
        }
        pasted.push(file);
      });
      if (pasted.length) {
        event.preventDefault();
        addFiles(pasted);
        dropzone.classList.add("is-pasted");
        setTimeout(function () { dropzone.classList.remove("is-pasted"); }, 600);
      }
    });
  }

  function initLinks(side) {
    var container = side.querySelector("[data-link-list]");
    var addButton = side.querySelector("[data-link-add]");
    if (!container || !addButton) { return; }

    addButton.addEventListener("click", function () {
      var template = container.querySelector(".link-row:last-child");
      var row = template.cloneNode(true);
      row.querySelector("input").value = "";
      container.appendChild(row);
      row.querySelector("input").focus();
    });

    container.addEventListener("click", function (event) {
      var button = event.target.closest("[data-link-remove]");
      if (!button) { return; }
      var row = button.closest(".link-row");
      if (container.querySelectorAll(".link-row").length > 1) {
        row.remove();
      } else {
        row.querySelector("input").value = "";
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var side = document.querySelector("[data-item-attachments]");
    if (!side) { return; }
    initAttachments(side);
    initLinks(side);
  });
})();
