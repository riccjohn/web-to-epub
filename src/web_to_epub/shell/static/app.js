(function () {
  "use strict";

  var EXT = /\.(md|markdown|txt)$/i;

  // Mirrors web_to_epub.core.ordering.natural_sort: casefolded text split on
  // digit runs (numbers compared numerically), ties broken by the raw name.
  function naturalKey(name) {
    return name.toLowerCase().split(/(\d+)/).map(function (p, i) {
      return i % 2 ? parseInt(p, 10) : p;
    });
  }
  function cmpStr(a, b) { return a < b ? -1 : a > b ? 1 : 0; }
  function naturalCompare(a, b) {
    var ka = naturalKey(a), kb = naturalKey(b);
    var n = Math.min(ka.length, kb.length);
    for (var i = 0; i < n; i++) {
      var c = i % 2 ? ka[i] - kb[i] : cmpStr(ka[i], kb[i]);
      if (c) return c < 0 ? -1 : 1;
    }
    if (ka.length !== kb.length) return ka.length < kb.length ? -1 : 1;
    return cmpStr(a, b);
  }
  function naturalSort(names) { return names.slice().sort(naturalCompare); }

  function move(arr, from, to) {
    if (from === to || from < 0 || to < 0 || from >= arr.length || to >= arr.length) return arr.slice();
    var out = arr.slice();
    out.splice(to, 0, out.splice(from, 1)[0]);
    return out;
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { naturalSort: naturalSort, naturalCompare: naturalCompare, move: move };
  }
  if (typeof document === "undefined") return;

  var $ = function (id) { return document.getElementById(id); };
  var items = []; // {file: File}
  var manual = false; // user has reordered by hand
  var dragIndex = -1;

  var SVG = '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">';
  var ICONS = {
    grip: '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false" fill="currentColor">' +
      '<circle cx="7" cy="5" r="1.5"/><circle cx="13" cy="5" r="1.5"/><circle cx="7" cy="10" r="1.5"/>' +
      '<circle cx="13" cy="10" r="1.5"/><circle cx="7" cy="15" r="1.5"/><circle cx="13" cy="15" r="1.5"/></svg>',
    up: SVG + '<path d="M10 16V4M5 9l5-5 5 5"/></svg>',
    down: SVG + '<path d="M10 4v12M5 11l5 5 5-5"/></svg>',
    x: SVG + '<path d="M5 5l10 10M15 5L5 15"/></svg>'
  };

  var list = $("file-list"), fileMsg = $("file-msg"), live = $("live");

  function show(el, text) { el.textContent = text || ""; el.hidden = !text; }

  function addFiles(fileList) {
    var rejected = [], dupes = [], fresh = [];
    Array.prototype.forEach.call(fileList, function (f) {
      if (!EXT.test(f.name)) { rejected.push(f.name); return; }
      var taken = items.some(function (it) { return it.file.name === f.name; }) ||
        fresh.some(function (it) { return it.file.name === f.name; });
      if (taken) { dupes.push(f.name); return; }
      fresh.push({ file: f });
    });
    items = manual ? items.concat(fresh.sort(byName)) : items.concat(fresh).sort(byName);
    var msgs = [];
    if (rejected.length) msgs.push("Skipped unsupported file type: " + rejected.join(", ") + ". Use .md, .markdown or .txt.");
    if (dupes.length) msgs.push("Skipped duplicate file name: " + dupes.join(", ") + ". Every file needs a unique name; rename it and add it again.");
    show(fileMsg, msgs.join(" "));
    render();
  }

  function announce(text) { live.textContent = ""; setTimeout(function () { live.textContent = text; }, 30); }

  function byName(a, b) { return naturalCompare(a.file.name, b.file.name); }

  function reorder(from, to) {
    var name = items[from].file.name;
    items = move(items, from, to);
    manual = true;
    render();
    announce(name + " moved to position " + (to + 1) + " of " + items.length);
  }

  function moveItem(from, to, focusKind) {
    if (to < 0 || to >= items.length) return;
    reorder(from, to);
    var btn = list.children[to].querySelector('[data-act="' + focusKind + '"]');
    if (btn && !btn.disabled) btn.focus();
    else list.children[to].querySelector(focusKind === "up" ? '[data-act="down"]' : '[data-act="up"]').focus();
  }

  function render() {
    list.textContent = "";
    items.forEach(function (it, i) {
      var li = document.createElement("li");
      li.dataset.index = i;

      var handle = document.createElement("span");
      handle.className = "handle"; handle.title = "Drag to reorder";
      handle.innerHTML = ICONS.grip;
      handle.setAttribute("aria-hidden", "true");
      handle.addEventListener("mousedown", function () { li.draggable = true; });
      handle.addEventListener("touchstart", function () { li.draggable = true; }, { passive: true });
      li.addEventListener("dragstart", function (e) {
        if (!li.draggable) { e.preventDefault(); return; }
        dragIndex = i; li.classList.add("dragging");
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", it.file.name);
      });
      li.addEventListener("dragend", function () {
        li.draggable = false; dragIndex = -1; clearMarks();
      });
      li.addEventListener("dragover", function (e) {
        if (dragIndex < 0) return;
        e.preventDefault(); e.stopPropagation();
        clearMarks();
        li.classList.add(dragIndex < i ? "drop-after" : "drop-before");
      });
      li.addEventListener("drop", function (e) {
        if (dragIndex < 0) return;
        e.preventDefault(); e.stopPropagation();
        var from = dragIndex; dragIndex = -1; clearMarks();
        if (from !== i) reorder(from, i);
      });

      var pos = document.createElement("span");
      pos.className = "pos"; pos.textContent = String(i + 1);
      pos.setAttribute("aria-hidden", "true");
      var name = document.createElement("span");
      name.className = "name"; name.textContent = it.file.name;

      name.title = it.file.name;
      var actions = document.createElement("span");
      actions.className = "actions";
      li.append(handle, pos, name, actions);
      actions.appendChild(button("up", ICONS.up, "Move " + it.file.name + " up", i === 0, function () { moveItem(i, i - 1, "up"); }));
      actions.appendChild(button("down", ICONS.down, "Move " + it.file.name + " down", i === items.length - 1, function () { moveItem(i, i + 1, "down"); }));
      actions.appendChild(button("remove", ICONS.x, "Remove " + it.file.name, false, function () {
        items.splice(i, 1); render();
        var next = list.children[Math.min(i, items.length - 1)];
        (next ? next.querySelector('[data-act="remove"]') : $("dropzone")).focus();
        announce(it.file.name + " removed");
      }));
      list.appendChild(li);
    });
    $("list-tools").hidden = items.length === 0;
    $("count").textContent = items.length + (items.length === 1 ? " file" : " files");
  }

  function clearMarks() {
    Array.prototype.forEach.call(list.children, function (li) {
      li.classList.remove("dragging", "drop-before", "drop-after");
    });
  }

  function button(act, text, label, disabled, onClick) {
    var b = document.createElement("button");
    b.type = "button"; b.dataset.act = act; b.className = "icon-btn"; b.innerHTML = text;
    b.setAttribute("aria-label", label); b.title = label; b.disabled = disabled;
    b.addEventListener("click", onClick);
    return b;
  }

  // Dropzone
  var dz = $("dropzone"), input = $("file-input");
  dz.addEventListener("click", function () { input.click(); });
  dz.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  input.addEventListener("change", function () { addFiles(input.files); input.value = ""; });
  ["dragenter", "dragover"].forEach(function (t) {
    dz.addEventListener(t, function (e) { e.preventDefault(); dz.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (t) {
    dz.addEventListener(t, function () { dz.classList.remove("over"); });
  });
  dz.addEventListener("drop", function (e) {
    e.preventDefault();
    if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  });
  // Stop the browser navigating to a file dropped outside the dropzone.
  ["dragover", "drop"].forEach(function (t) {
    window.addEventListener(t, function (e) { if (dragIndex < 0) e.preventDefault(); });
  });

  $("sort-btn").addEventListener("click", function () {
    items.sort(byName);
    manual = false; render(); announce("Sorted naturally");
  });
  $("clear-btn").addEventListener("click", function () {
    items = []; manual = false; render(); dz.focus();
  });

  // Build
  var form = $("form"), errorEl = $("error"), warnEl = $("warnings"),
    statusEl = $("status"), progress = $("progress"), buildBtn = $("build-btn");

  function fail(msg, field) {
    show(errorEl, msg);
    if (field) {
      field.setAttribute("aria-invalid", "true");
      var inline = $(field.id + "-err");
      if (inline) show(inline, msg);
      field.focus();
    }
  }

  function clearInvalid(id) {
    $(id).removeAttribute("aria-invalid"); show($(id + "-err"), "");
  }

  ["title", "author"].forEach(function (id) {
    $(id).addEventListener("input", function () { clearInvalid(id); });
  });

  var btnLabel = buildBtn.querySelector(".label");
  function setBuilding(on) {
    buildBtn.disabled = on; progress.hidden = !on;
    buildBtn.classList.toggle("busy", on);
    buildBtn.setAttribute("aria-busy", on ? "true" : "false");
    btnLabel.textContent = on ? "Building\u2026" : "Build EPUB";
  }

  function filenameFrom(resp) {
    var m = /filename="?([^";]+)"?/.exec(resp.headers.get("Content-Disposition") || "");
    return m ? m[1] : "book.epub";
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    show(errorEl, ""); show(warnEl, ""); show(statusEl, "");
    ["title", "author"].forEach(clearInvalid);
    statusEl.classList.remove("ok");

    if (!$("title").value.trim()) return fail("A title is required", $("title"));
    if (!$("author").value.trim()) return fail("An author is required", $("author"));
    if (!items.length) return fail("Add at least one chapter file", dz);

    var fd = new FormData();
    items.forEach(function (it) { fd.append("files", it.file, it.file.name); });
    fd.append("order", JSON.stringify(items.map(function (it) { return it.file.name; })));
    fd.append("title", $("title").value.trim());
    fd.append("author", $("author").value.trim());
    ["language", "description", "strip_suffix"].forEach(function (id) {
      var v = $(id).value.trim();
      if (v) fd.append(id, v);
    });
    var cover = $("cover").files[0];
    if (cover) fd.append("cover", cover, cover.name);

    setBuilding(true);
    show(statusEl, "Building EPUB...");

    fetch("/convert", { method: "POST", body: fd }).then(function (resp) {
      if (!resp.ok) {
        return resp.json().then(function (j) { return j.error; }, function () { return null; })
          .then(function (msg) { throw new Error(msg || "Build failed (HTTP " + resp.status + ")"); });
      }
      var warnings = parseInt(resp.headers.get("X-Warnings") || "0", 10) || 0;
      var fname = filenameFrom(resp);
      return resp.blob().then(function (blob) {
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url; a.download = fname;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
        show(statusEl, "Done. Downloaded " + fname + ".");
        statusEl.classList.add("ok");
        if (warnings > 0) {
          show(warnEl, warnings + (warnings === 1 ? " image" : " images") +
            " could not be fetched or used. Check your image links.");
        }
      });
    }).catch(function (err) {
      show(statusEl, "");
      fail(err instanceof TypeError ? "Could not reach the server." : err.message);
    }).then(function () {
      setBuilding(false);
    });
  });

  render();
})();
