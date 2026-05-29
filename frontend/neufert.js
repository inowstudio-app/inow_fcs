/* Neufert Data tab — grounded Q&A over the architect reference books.
   Separate <script> so it never disturbs app.js. View switching + layout are
   handled natively by app.js (the tab handler + showView now include "neufert");
   this file only lazy-loads the topic list and runs the ask/render logic. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var topicsData = null;       // {books, chapters}
  var loaded = false;
  var history = [];            // [{role, text}]
  var sketchFile = null;

  function esc(s) {
    return (s || "").replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // ---- topic list ----
  function loadTopics() {
    if (loaded) return;
    var sel = $("nfTopic");
    fetch("/api/books/topics").then(function (r) {
      if (!r.ok) throw new Error("topics " + r.status);
      return r.json();
    }).then(function (data) {
      topicsData = data; loaded = true;
      var bsel = $("nfBook");
      (data.books || []).forEach(function (b) {
        var o = document.createElement("option");
        o.value = b.id; o.textContent = b.label + " (" + b.pages + " pp)";
        bsel.appendChild(o);
      });
      renderTopics();
    }).catch(function (e) {
      loaded = false;
      var notice = $("nfNotice");
      if (notice) {
        notice.hidden = false;
        notice.textContent = "Could not load book topics (" + e.message +
          "). Make sure the ingest has run and the server is up.";
      }
      if (sel) sel.innerHTML = '<option value="">— unavailable —</option>';
    });
  }

  function renderTopics() {
    var sel = $("nfTopic");
    if (!sel || !topicsData) return;
    var bookFilter = $("nfBook").value;
    var q = ($("nfSearch").value || "").trim().toLowerCase();
    sel.innerHTML = "";
    var byBook = {};
    (topicsData.books || []).forEach(function (b) { byBook[b.id] = b.label; });
    var shown = 0;
    (topicsData.chapters || []).forEach(function (ch) {
      if (shown > 1500) return;                 // safety cap on very broad filters
      if (bookFilter && ch.book !== bookFilter) return;
      var items = [{ title: ch.title, page: ch.page, page_end: ch.page_end, lvl: 0 }];
      (ch.children || []).forEach(function (c) {
        items.push({ title: c.title, page: c.page, page_end: c.page_end, lvl: 1 });
      });
      var matched = q ? items.filter(function (it) {
        return (it.title || "").toLowerCase().indexOf(q) >= 0;
      }) : items;
      if (!matched.length) return;
      var og = document.createElement("optgroup");
      og.label = (byBook[ch.book] || ch.book) + " · " + ch.title;
      matched.forEach(function (it) {
        var o = document.createElement("option");
        o.value = [ch.book, it.page, it.page_end || it.page, it.title].join("|");
        o.textContent = (it.lvl ? "   " : "") + it.title + "  (p." + it.page + ")";
        og.appendChild(o);
        shown++;
      });
      sel.appendChild(og);
    });
    if (!sel.children.length) sel.innerHTML = '<option value="">— no topics match —</option>';
    onTopicChange();
  }

  function selectedTopic() {
    var sel = $("nfTopic");
    if (!sel || !sel.value) return null;
    var p = sel.value.split("|");
    return { book: p[0], page: parseInt(p[1], 10), page_end: parseInt(p[2], 10), title: p[3] };
  }

  function onTopicChange() {
    var t = selectedTopic();
    var lab = $("nfTopicSel");
    if (lab) lab.textContent = t ? ("Topic: " + t.title) : "No topic selected";
  }

  // ---- canvas (book pages, sketch, diagram) ----
  function pushCanvas(html) {
    var c = $("nfCanvas");
    if (!c) return;
    var ph = c.querySelector(".placeholder");
    if (ph) ph.remove();
    var div = document.createElement("div");
    div.innerHTML = html;
    c.appendChild(div);
    c.scrollTop = c.scrollHeight;
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return;
    var chips = sources.map(function (s) {
      return '<span class="src-chip" data-url="' + s.url + '">' + esc(s.label) + "</span>";
    }).join("");
    pushCanvas('<div class="src-row">' + chips + "</div>");
    $("nfCanvas").querySelectorAll(".src-chip").forEach(function (ch) {
      if (ch._wired) return; ch._wired = true;
      ch.addEventListener("click", function () {
        pushCanvas('<img class="bookpage" src="' + ch.getAttribute("data-url") + '" />');
      });
    });
  }

  // ---- thread ----
  function pushThread(role, text) {
    var th = $("nfThread");
    if (!th) return;
    var div = document.createElement("div");
    div.className = "bubble " + (role === "user" ? "you" : "dcr");
    div.innerHTML = "<b>" + (role === "user" ? "You" : "Assistant") + ":</b> " +
      esc(text).replace(/\n/g, "<br>");
    th.appendChild(div);
    th.scrollTop = th.scrollHeight;
    return div;
  }

  // ---- ask ----
  function ask() {
    var qEl = $("nfQ");
    var question = (qEl.value || "").trim();
    if (!question) { qEl.focus(); return; }
    var topic = selectedTopic();
    var send = $("nfSend");
    send.disabled = true; var oldLabel = send.textContent; send.textContent = "…";

    pushThread("user", question + (topic ? "  [" + topic.title + "]" : ""));
    if (sketchFile) {
      var fr = new FileReader();
      fr.onload = function (e) {
        pushCanvas('<div class="hint">Your sketch:</div><img class="bookpage" src="' + e.target.result + '" />');
      };
      fr.readAsDataURL(sketchFile);
    }
    var thinking = pushThread("assistant", "…thinking…");

    var fd = new FormData();
    fd.append("question", question);
    if (topic) {
      fd.append("book", topic.book);
      fd.append("topic_title", topic.title);
      fd.append("topic_page", topic.page);
      fd.append("topic_page_end", topic.page_end);
    }
    fd.append("history", JSON.stringify(history.slice(-6)));
    if (sketchFile) fd.append("sketch", sketchFile);

    fetch("/api/books/ask", { method: "POST", body: fd })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (thinking) thinking.remove();
        if (!res.ok) throw new Error(res.j.detail || "request failed");
        var ans = res.j.answer || "(no answer)";
        pushThread("assistant", ans);
        history.push({ role: "user", text: question });
        history.push({ role: "assistant", text: ans });
        renderSources(res.j.sources);
        if (res.j.svg) pushCanvas('<div class="hint">Diagram:</div>' + res.j.svg);
        qEl.value = "";
        sketchFile = null;
        $("nfImgName").textContent = "";
      })
      .catch(function (e) {
        if (thinking) thinking.remove();
        pushThread("assistant", "⚠ " + e.message);
      })
      .finally(function () { send.disabled = false; send.textContent = oldLabel; });
  }

  // ---- init ----
  function init() {
    var tabBtn = document.querySelector('[data-view="neufert"]');
    if (tabBtn) tabBtn.addEventListener("click", loadTopics);   // lazy-load on first open

    var b = $("nfBook"); if (b) b.addEventListener("change", renderTopics);
    var s = $("nfSearch"); if (s) s.addEventListener("input", renderTopics);
    var t = $("nfTopic"); if (t) t.addEventListener("change", onTopicChange);
    var send = $("nfSend"); if (send) send.addEventListener("click", ask);
    var q = $("nfQ");
    if (q) q.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); ask(); }
    });
    var img = $("nfImg");
    if (img) img.addEventListener("change", function () {
      sketchFile = img.files[0] || null;
      $("nfImgName").textContent = sketchFile ? ("Attached: " + sketchFile.name) : "";
    });
    var nc = $("nfNewChat");
    if (nc) nc.addEventListener("click", function () {
      history = [];
      $("nfThread").innerHTML = "";
      $("nfCanvas").innerHTML = '<p class="placeholder">Cited book pages, diagrams the assistant draws, and sketches you attach appear here — large.</p>';
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
