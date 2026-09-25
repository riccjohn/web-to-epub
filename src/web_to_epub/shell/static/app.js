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
  var items = []; // {file: File, url?: string (fetched pages), text?: string, open?: bool}
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

  // Shared by dropped files and fetched pages. entries: [{file, url?, text?}].
  function addEntries(entries) {
    var rejected = [], dupes = [], fresh = [];
    entries.forEach(function (en) {
      var f = en.file;
      if (!EXT.test(f.name)) { rejected.push(f.name); return; }
      var taken = items.some(function (it) { return it.file.name === f.name; }) ||
        fresh.some(function (it) { return it.file.name === f.name; });
      if (taken) { dupes.push(f.name); return; }
      fresh.push(en);
    });
    items = manual ? items.concat(fresh.sort(byName)) : items.concat(fresh).sort(byName);
    render();
    return { rejected: rejected, dupes: dupes, added: fresh.length };
  }

  function addFiles(fileList) {
    var r = addEntries(Array.prototype.map.call(fileList, function (f) { return { file: f }; }));
    var rejected = r.rejected, dupes = r.dupes;
    var msgs = [];
    if (rejected.length) msgs.push("Skipped unsupported file type: " + rejected.join(", ") + ". Use .md, .markdown or .txt.");
    if (dupes.length) msgs.push("Skipped duplicate file name: " + dupes.join(", ") + ". Every file needs a unique name; rename it and add it again.");
    show(fileMsg, msgs.join(" "));
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
      var info = document.createElement("span");
      info.className = "info";
      info.appendChild(name);
      if (it.url) info.appendChild(sourceRow(it));
      var actions = document.createElement("span");
      actions.className = "actions";
      li.append(handle, pos, info, actions);
      actions.appendChild(button("up", ICONS.up, "Move " + it.file.name + " up", i === 0, function () { moveItem(i, i - 1, "up"); }));
      actions.appendChild(button("down", ICONS.down, "Move " + it.file.name + " down", i === items.length - 1, function () { moveItem(i, i + 1, "down"); }));
      actions.appendChild(button("remove", ICONS.x, "Remove " + it.file.name, false, function () {
        items.splice(i, 1); render();
        var next = list.children[Math.min(i, items.length - 1)];
        (next ? next.querySelector('[data-act="remove"]') : $("dropzone")).focus();
        announce(it.file.name + " removed");
      }));
      if (it.url) li.classList.add("fetched");
      if (it.url && it.open) li.appendChild(editPanel(it, i));
      list.appendChild(li);
    });
    $("list-tools").hidden = items.length === 0;
    $("list-h").hidden = items.length === 0;
    $("count").textContent = items.length + (items.length === 1 ? " chapter" : " chapters");
  }

  // Badge, source URL and the Preview / Edit toggle for a fetched page.
  function sourceRow(it) {
    var row = document.createElement("span");
    row.className = "src-row";
    var badge = document.createElement("span");
    badge.className = "badge"; badge.textContent = "from web";
    var src = document.createElement("span");
    src.className = "src"; src.textContent = it.url; src.title = it.url;
    var t = document.createElement("button");
    t.type = "button"; t.className = "edit-toggle"; t.dataset.act = "edit";
    t.textContent = "Preview / Edit";
    t.setAttribute("aria-expanded", it.open ? "true" : "false");
    t.setAttribute("aria-controls", "edit-" + items.indexOf(it));
    t.setAttribute("aria-label", "Preview or edit " + it.file.name);
    t.addEventListener("click", function () {
      it.open = !it.open; render();
      var b = list.children[items.indexOf(it)].querySelector('[data-act="edit"]');
      if (b) b.focus();
    });
    row.append(badge, src, t);
    return row;
  }

  function editPanel(it, i) {
    var wrap = document.createElement("div");
    wrap.className = "edit-panel"; wrap.id = "edit-" + i;
    var lab = document.createElement("label");
    lab.htmlFor = "edit-ta-" + i;
    lab.textContent = "Markdown for " + it.file.name + " (what you edit here is what gets built)";
    var ta = document.createElement("textarea");
    ta.id = "edit-ta-" + i; ta.rows = 14; ta.spellcheck = false; ta.value = it.text;
    ta.addEventListener("input", function () {
      it.text = ta.value;
      it.file = new File([ta.value], it.file.name, { type: it.file.type || "text/markdown" });
    });
    wrap.append(lab, ta);
    return wrap;
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
    items = []; manual = false; render(); dz.focus(); announce("All chapters removed");
  });

  // URL rows and fetching
  var urlRows = $("url-rows"), urlMsg = $("url-msg"), urlErrors = $("url-errors"),
    fetchBtn = $("fetch-btn"), rowSeq = 0, fetching = false;

  function rowInputs() { return Array.prototype.slice.call(urlRows.querySelectorAll("input")); }

  function relabel() {
    var lis = urlRows.children, n = lis.length;
    Array.prototype.forEach.call(lis, function (li, k) {
      li.querySelector("label").textContent = "Web page URL " + (k + 1);
      var rm = li.querySelector("button");
      rm.setAttribute("aria-label", "Remove URL " + (k + 1));
      rm.title = "Remove URL " + (k + 1);
      rm.disabled = n === 1;
    });
  }

  function addRow(value, focus) {
    var id = "url-" + (++rowSeq);
    var li = document.createElement("li");
    li.className = "url-row";
    var lab = document.createElement("label");
    lab.className = "sr-only"; lab.htmlFor = id;
    var inp = document.createElement("input");
    inp.type = "text"; inp.id = id; inp.inputMode = "url"; inp.autocomplete = "off";
    inp.spellcheck = false; inp.placeholder = "https://example.com/page"; inp.value = value || "";
    inp.addEventListener("input", function () { inp.removeAttribute("aria-invalid"); });
    inp.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      e.preventDefault(); // never submit the build form from a URL box
      var all = rowInputs(), k = all.indexOf(inp);
      if (k < all.length - 1) all[k + 1].focus();
      else if (inp.value.trim()) { addRow("", true); announce("URL " + (all.length + 1) + " added"); }
      else fetchPages();
    });
    var rm = document.createElement("button");
    rm.type = "button"; rm.className = "icon-btn"; rm.innerHTML = ICONS.x;
    rm.addEventListener("click", function () {
      if (urlRows.children.length === 1) return;
      var k = Array.prototype.indexOf.call(urlRows.children, li);
      li.remove(); relabel();
      var all = rowInputs();
      all[Math.min(k, all.length - 1)].focus();
      announce("URL removed. " + all.length + (all.length === 1 ? " URL row" : " URL rows") + " left");
    });
    li.append(lab, inp, rm);
    urlRows.appendChild(li);
    relabel();
    if (focus) inp.focus();
    return inp;
  }

  $("add-url-btn").addEventListener("click", function () {
    addRow("", true);
    announce("URL " + urlRows.children.length + " added");
  });

  function setFetching(on) {
    fetching = on;
    fetchBtn.disabled = on;
    fetchBtn.classList.toggle("busy", on);
    fetchBtn.setAttribute("aria-busy", on ? "true" : "false");
    fetchBtn.querySelector(".label").textContent = on ? "Fetching…" : "Fetch pages";
  }

  function showErrors(errs) {
    urlErrors.textContent = "";
    errs.forEach(function (er) {
      var li = document.createElement("li");
      var u = document.createElement("strong"); u.textContent = er.url;
      li.append(u, document.createTextNode(": " + er.message));
      urlErrors.appendChild(li);
    });
    urlErrors.hidden = errs.length === 0;
  }

  function collectUrls() {
    var seen = {}, urls = [], skipped = [];
    rowInputs().forEach(function (inp) {
      var u = inp.value.trim();
      if (!u || seen[u]) return;
      seen[u] = true;
      if (items.some(function (it) { return it.url === u; })) skipped.push(u);
      else urls.push(u);
    });
    return { urls: urls, skipped: skipped };
  }

  // Resolves to the number of URLs that failed (0 = everything typed was fetched or already added).
  function fetchPages() {
    if (fetching) return Promise.resolve(1);
    show(urlMsg, ""); showErrors([]);
    var collected = collectUrls(), urls = collected.urls, skipped = collected.skipped;
    if (!urls.length) {
      show(urlMsg, skipped.length ? "Already added: " + skipped.join(", ") + "." : "Enter at least one URL to fetch.");
      if (!skipped.length) rowInputs()[0].focus();
      return Promise.resolve(0);
    }
    setFetching(true);
    announce("Fetching " + urls.length + (urls.length === 1 ? " page" : " pages"));

    return fetch("/fetch", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: urls }) }).then(function (resp) {
      return resp.json().then(function (j) { return { ok: resp.ok, status: resp.status, j: j }; },
        function () { return { ok: false, status: resp.status, j: null }; });
    }).then(function (r) {
      if (!r.ok) throw new Error((r.j && r.j.error) || "Fetch failed (HTTP " + r.status + ")");
      var chapters = r.j.chapters || [], errs = r.j.errors || [];
      var entries = [], already = skipped.slice();
      chapters.forEach(function (c) {
        if (items.some(function (it) { return it.url === c.url; })) { already.push(c.url); return; }
        entries.push({ file: new File([c.markdown], c.filename, { type: "text/markdown" }),
          url: c.url, text: c.markdown, open: false });
      });
      var res = addEntries(entries);
      var msgs = [];
      if (already.length) msgs.push("Already added: " + already.join(", ") + ".");
      if (res.dupes.length) msgs.push("Skipped duplicate file name: " + res.dupes.join(", ") + ". Every chapter needs a unique name; remove the existing one first.");
      if (res.rejected.length) msgs.push("Skipped unsupported file type: " + res.rejected.join(", ") + ".");
      show(urlMsg, msgs.join(" "));
      showErrors(errs);
      // Drop rows that were fetched; keep failed ones so they can be fixed.
      var bad = {};
      errs.forEach(function (er) { bad[er.url] = true; });
      var keep = rowInputs().map(function (i) { return i.value; })
        .filter(function (v) { return bad[v.trim()]; });
      urlRows.textContent = "";
      if (!keep.length) addRow("", false);
      keep.forEach(function (v) { addRow(v, false).setAttribute("aria-invalid", "true"); });
      var n = res.added;
      announce("Fetched " + n + (n === 1 ? " page" : " pages") +
        (errs.length ? ", " + errs.length + " failed" : "") + ".");
      if (errs.length || !n) rowInputs()[0].focus();
      return errs.length || (n ? 0 : 1);
    }).catch(function (err) {
      var msg = err instanceof TypeError ? "Could not reach the server." : err.message;
      show(urlMsg, msg); announce("Fetch failed. " + msg);
      return 1;
    }).then(function (failed) { setFetching(false); return failed; });
  }
  fetchBtn.addEventListener("click", function () { fetchPages(); });
  addRow("", false);

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

    // URLs typed but not fetched yet are fetched now, so Build never silently ignores them.
    if (collectUrls().urls.length) {
      if (fetching) return;
      setBuilding(true);
      show(statusEl, "Fetching pages...");
      fetchPages().then(function (failed) {
        setBuilding(false);
        show(statusEl, "");
        if (failed) return fail("Some pages could not be fetched. Fix or remove them, then build again.");
        buildBook();
      });
      return;
    }
    buildBook();
  });

  function buildBook() {
    if (!items.length) return fail("Add at least one chapter (upload a file or fetch a web page)", dz);

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
  }

  render();
})();
