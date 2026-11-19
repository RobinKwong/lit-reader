/* lit_reader: reading controls. No network access, no dependencies.
   Stores preferences, reading position and status in localStorage,
   wrapped in try/catch so the page still works when storage is blocked. */
(function () {
  "use strict";
  var WPM = 200; // academic prose; an estimate, labelled as one
  var root = document.documentElement;
  var pid = document.body.getAttribute("data-pid") || "";

  function load(key, dflt) {
    try { var v = localStorage.getItem(key); return v === null ? dflt : JSON.parse(v); }
    catch (e) { return dflt; }
  }
  function save(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); return true; } catch (e) { return false; } }

  /* ---------- preferences ---------- */
  var PREF_KEY = "litreader.prefs";
  var prefs = load(PREF_KEY, {});
  var SIZES = [16, 17, 18, 19, 20, 21, 22, 24, 26];
  var WIDTHS = { narrow: "47ch", medium: "54ch", wide: "62ch" };
  var LHS = { tight: 1.4, normal: 1.5, loose: 1.7 };

  function applyPrefs() {
    if (prefs.theme && prefs.theme !== "auto") root.setAttribute("data-theme", prefs.theme);
    else root.removeAttribute("data-theme");
    if (prefs.font && prefs.font !== "literata") root.setAttribute("data-font", prefs.font);
    else root.removeAttribute("data-font");
    if (prefs.para === "orig") root.setAttribute("data-para", "orig");
    else root.removeAttribute("data-para");
    root.style.setProperty("--size", (prefs.size || 20) + "px");
    root.style.setProperty("--measure", WIDTHS[prefs.width || "medium"]);
    root.style.setProperty("--lh", LHS[prefs.lh || "normal"]);
    document.querySelectorAll(".panel [data-pref]").forEach(function (b) {
      var k = b.getAttribute("data-pref"), v = b.getAttribute("data-val");
      var cur = prefs[k] || { theme: "auto", font: "literata", width: "medium", lh: "normal", para: "short" }[k];
      b.setAttribute("aria-pressed", String(cur === v));
    });
    var sz = document.getElementById("size-now");
    if (sz) sz.textContent = (prefs.size || 20) + "px";
  }
  applyPrefs();

  var panel = document.getElementById("panel");
  var aa = document.getElementById("aa");
  function setPanel(open, refocus) {
    panel.hidden = !open;
    aa.setAttribute("aria-expanded", String(open));
    if (!open && refocus) aa.focus();
  }
  if (aa && panel) {
    aa.addEventListener("click", function (e) { e.stopPropagation(); setPanel(panel.hidden); });
    document.addEventListener("click", function (e) { if (!panel.hidden && !panel.contains(e.target)) setPanel(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) setPanel(false, true); });
    panel.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      if (b.hasAttribute("data-pref")) prefs[b.getAttribute("data-pref")] = b.getAttribute("data-val");
      if (b.id === "size-down" || b.id === "size-up") {
        var i = SIZES.indexOf(prefs.size || 20); if (i < 0) i = 4;
        i = Math.max(0, Math.min(SIZES.length - 1, i + (b.id === "size-up" ? 1 : -1)));
        prefs.size = SIZES[i];
      }
      var anchor = pid && latest && document.getElementById(latest.id);  // the text you were reading stays where it is
      var was = anchor ? anchor.getBoundingClientRect().top : 0;
      save(PREF_KEY, prefs); applyPrefs();
      if (anchor) window.scrollBy(0, anchor.getBoundingClientRect().top - was);
      if (pid) { measure(); update(); }
    });
  }

  if (!pid) {
    // the index page: show each paper's reading status
    document.querySelectorAll(".list li[data-pid]").forEach(function (li) {
      var st = load("litreader.status." + li.getAttribute("data-pid"), {});
      var s = li.querySelector(".s"); if (!s || !st.state) return;
      s.textContent = st.state === "done" ? "Finished" : "In progress";
      s.className = "s " + (st.state === "done" ? "done" : "started");
    });
    return;
  }

  /* ---------- contents drawer on narrow screens ---------- */
  var toc = document.querySelector("nav.toc");
  var tocToggle = document.getElementById("toc-toggle");
  function setToc(open, refocus) {
    toc.classList.toggle("open", open);
    tocToggle.setAttribute("aria-expanded", String(open));
    if (open) { var first = toc.querySelector("a"); if (first) setTimeout(function () { first.focus(); }, 30); }
    if (!open && refocus) tocToggle.focus();
  }
  if (tocToggle && toc) {
    tocToggle.addEventListener("click", function (e) { e.stopPropagation(); setToc(!toc.classList.contains("open")); });
    toc.addEventListener("click", function (e) {
      var a = e.target.closest("a"); if (!a) return;
      setToc(false);
      var to = a.hash && document.getElementById(a.hash.slice(1));  // keyboard focus moves with the jump
      if (to) { to.tabIndex = -1; setTimeout(function () { to.focus({ preventScroll: true }); }, 30); }
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && toc.classList.contains("open")) setToc(false, true); });
  }

  /* ---------- sidenotes on narrow screens ---------- */
  document.addEventListener("click", function (e) {
    var m = e.target.closest(".sn-mark"); if (!m) return;
    var n = document.getElementById(m.getAttribute("data-for"));
    if (!n) return;
    if (getComputedStyle(n).float === "none") { m.setAttribute("aria-expanded", String(n.classList.toggle("open"))); return; }
    n.classList.add("flash");  // already in the margin: show which note this mark belongs to
    setTimeout(function () { n.classList.remove("flash"); }, 1600);
  });
  document.querySelectorAll(".sn-mark").forEach(function (m) {
    var n = document.getElementById(m.getAttribute("data-for"));
    if (n && getComputedStyle(n).float === "none") m.setAttribute("aria-expanded", "false");
  });
  document.addEventListener("keydown", function (e) {
    var m = e.target.closest && e.target.closest(".sn-mark");
    if (m && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); m.click(); }
    if (m && e.key === "Escape") {
      var n = document.getElementById(m.getAttribute("data-for"));
      if (n && n.classList.contains("open")) { n.classList.remove("open"); m.setAttribute("aria-expanded", "false"); }
    }
  });

  /* ---------- citation cards ---------- */
  var card = null, cardFrom = null;
  function closeCard(refocus) {
    if (!card) return;
    card.remove(); card = null;
    if (refocus && cardFrom) cardFrom.focus();
  }
  document.querySelectorAll("a.cite").forEach(function (a) {
    a.setAttribute("aria-haspopup", "dialog");
    if (/^\d/.test(a.textContent)) a.setAttribute("aria-label", "Reference " + a.textContent);
  });
  function openCard(a, moveFocus) {
    closeCard();
    cardFrom = a;
    var ids = (a.getAttribute("data-ref") || "").split(" ").filter(Boolean);
    if (!ids.length) return;
    card = document.createElement("div");
    card.className = "cite-card";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-label", "Reference");
    card.tabIndex = -1;
    ids.forEach(function (id, i) {
      var li = document.getElementById("ref-" + id);
      if (!li) return;
      var d = document.createElement("div");
      if (i) d.style.marginTop = ".6rem";
      d.innerHTML = li.innerHTML; // our own sanitised reference list, not source HTML
      var go = document.createElement("a");
      go.href = "#ref-" + id; go.className = "go"; go.textContent = "Go to reference list";
      go.addEventListener("click", function () {
        closeCard(); li.classList.add("flash"); setTimeout(function () { li.classList.remove("flash"); }, 1600);
        var det = li.closest("details"); if (det) det.open = true;
        li.tabIndex = -1; setTimeout(function () { li.focus(); }, 30);
      });
      d.appendChild(go);
      card.appendChild(d);
    });
    if (!card.childNodes.length) { card = null; return; }
    document.body.appendChild(card);
    var r = a.getBoundingClientRect();
    var top = window.scrollY + r.bottom + 6;
    if (r.bottom + 6 + card.offsetHeight > window.innerHeight) top = Math.max(window.scrollY + 56, window.scrollY + r.top - card.offsetHeight - 6);
    var left = Math.min(window.scrollX + r.left, window.scrollX + document.documentElement.clientWidth - card.offsetWidth - 12);
    card.style.top = top + "px"; card.style.left = Math.max(8, left) + "px";
    card.addEventListener("keydown", function (e) {
      if (e.key !== "Tab") return;
      var links = card.querySelectorAll("a"), last = links[links.length - 1];
      if ((!e.shiftKey && document.activeElement === last) || (e.shiftKey && document.activeElement === card)) { e.preventDefault(); closeCard(true); }
    });
    if (moveFocus) card.focus();
  }
  var hoverTimer = null;
  document.addEventListener("mouseover", function (e) {
    var a = e.target.closest && e.target.closest("a.cite");
    if (a) { clearTimeout(hoverTimer); hoverTimer = setTimeout(function () { openCard(a); }, 250); }
  });
  document.addEventListener("mouseout", function (e) {
    var a = e.target.closest && e.target.closest("a.cite");
    if (a) clearTimeout(hoverTimer);
  });
  document.addEventListener("click", function (e) {
    var a = e.target.closest("a.cite");
    if (a) { e.preventDefault(); openCard(a, e.detail === 0); return; }  // detail 0: opened from the keyboard
    if (card && !card.contains(e.target)) closeCard();
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeCard(true); });

  /* ---------- saved quotes ----------
     Select text and choose "Save quote" (or press Q). Quotes stay in this
     browser, per paper, with the section and printed page they came from. */
  var CLIP_KEY = "litreader.clips." + pid;
  function loadClips() { var v = load(CLIP_KEY, []); return Array.isArray(v) ? v : []; }  // anything else in storage is ignored, not trusted
  var clips = loadClips();
  var clipsBtn = document.getElementById("clips");
  var clipsPanel = document.getElementById("clips-panel");
  var clipCount = document.getElementById("clip-count");
  var cite = document.body.getAttribute("data-cite") || "";
  var reference = document.body.getAttribute("data-reference") || document.title;
  var saveBtn = null, pending = null, stored = true;  // stored: false once the browser refuses to keep quotes

  function quoteText(range) {
    var div = document.createElement("div");
    div.appendChild(range.cloneContents());
    div.querySelectorAll(".sidenote, .sn-mark, .pg, details, button, .clip-save").forEach(function (n) { n.remove(); });
    div.querySelectorAll("p, li, .chunk, h2, h3, h4, figcaption, td, th").forEach(function (n) { n.appendChild(document.createTextNode(" ")); });
    return div.textContent.replace(/\s+/g, " ").trim();
  }
  function pageBefore(el) {
    var pgs = document.querySelectorAll("main .pg"), found = "";
    for (var i = 0; i < pgs.length; i++) {
      if (pgs[i].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) found = pgs[i].textContent.trim();
      else break;
    }
    return found.replace(/^p\.\s*/, "");
  }
  function locate(range) {
    var n = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentNode;
    var block = n.closest("main [data-w], main [data-sec], main section.abstract");
    if (!block) {  // a selection that starts between paragraphs: the first paragraph it reaches
      var all = document.querySelectorAll("main [data-w]");
      for (var k = 0; k < all.length && !block; k++) if (range.intersectsNode(all[k])) block = all[k];
    }
    var page = block ? pageBefore(block) : "";
    var div = document.createElement("div");
    div.appendChild(range.cloneContents());
    var inner = div.querySelectorAll(".pg");
    var last = inner.length ? inner[inner.length - 1].textContent.trim().replace(/^p\.\s*/, "") : "";
    if (last && page && last !== page) page = page + "–" + last;
    else if (last && !page) page = last;
    return { block: block ? block.id : "", sec: block && block.classList.contains("abstract") ? (block.querySelector("h2") || {}).textContent || "Abstract"
         : block && block.getAttribute("data-in") ? sectionTitle(block.getAttribute("data-in")) : "", page: page };
  }
  function citeFor(c) {
    return "(" + cite + (c.page ? (c.page.indexOf("–") > 0 ? ", pp. " : ", p. ") + c.page : "") + ")";
  }
  function asText(c) { return "“" + c.text + "” " + citeFor(c); }
  function asMarkdown() {
    var out = ["# Quotes from " + document.title, "", reference, ""];
    clips.forEach(function (c) {
      out.push("> " + c.text, "", citeFor(c) + (c.sec ? " · " + c.sec : ""), "");
    });
    return out.join("\n");
  }
  function copy(text) {
    function fallback() {
      var t = document.createElement("textarea"), ok = false; t.value = text; t.setAttribute("readonly", "");
      t.style.position = "fixed"; t.style.opacity = "0"; document.body.appendChild(t); t.select();
      try { ok = document.execCommand("copy"); } catch (e) {}
      t.remove();
      return ok;
    }
    function done(ok) { toast(ok ? "<span>Copied.</span>" : "<span>Couldn't copy. Use Download as Markdown instead.</span>", ok ? 2500 : 5000); }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(fallback()); });
    else done(fallback());
  }
  function hideSave() { if (saveBtn) { saveBtn.remove(); saveBtn = null; } pending = null; }
  function saveClip() {
    if (!pending) return;
    var c = pending;
    c.id = String(Date.now());
    c.at = new Date().toISOString();
    if (stored) clips = loadClips();  // another tab may have saved quotes since this one loaded
    clips.push(c); stored = save(CLIP_KEY, clips);
    hideSave();
    var sel = window.getSelection(); if (sel) sel.removeAllRanges();
    renderClips();
    toast(stored ? "<span>Quote saved. Open Quotes in the top bar to copy it with its citation.</span>"
                 : "<span>This browser won't keep quotes for local pages, so they last only until you close this tab. Open Quotes to copy or download them now.</span>", stored ? 4000 : 9000);
  }
  function renderClips() {
    if (clipCount) clipCount.textContent = clips.length ? "(" + clips.length + ")" : "";
    if (!clipsPanel) return;
    clipsPanel.innerHTML = "";
    var h = document.createElement("div"); h.className = "clips-head";
    h.textContent = clips.length ? "Saved quotes" : "No saved quotes yet";
    clipsPanel.appendChild(h);
    if (!clips.length) {
      var p = document.createElement("p"); p.className = "note";
      p.textContent = "Select text in the paper, then choose Save quote or press Q. Quotes stay in this browser.";
      clipsPanel.appendChild(p);
      return;
    }
    var all = document.createElement("div"); all.className = "row";
    [["Copy all", function () { copy(asMarkdown()); }],
     ["Download as Markdown", function () {
       var a = document.createElement("a");
       a.href = URL.createObjectURL(new Blob([asMarkdown()], { type: "text/markdown" }));
       a.download = "quotes-" + (document.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40) || "paper") + ".md";
       document.body.appendChild(a); a.click(); a.remove();
       setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
     }]].forEach(function (x) {
      var b = document.createElement("button"); b.type = "button"; b.textContent = x[0];
      b.addEventListener("click", x[1]); all.appendChild(b);
    });
    clipsPanel.appendChild(all);
    var ol = document.createElement("ol"); ol.className = "clips";
    clips.forEach(function (c, i) {
      var li = document.createElement("li");
      var q = document.createElement("blockquote"); q.textContent = c.text;
      var m = document.createElement("div"); m.className = "note";
      m.textContent = citeFor(c) + (c.sec ? " · " + c.sec : "");
      var acts = document.createElement("div"); acts.className = "acts";
      [["Copy", function () { copy(asText(c) + "\n\n" + reference); }],
       ["Go to", function () {
         setClips(false);
         var el = document.getElementById(c.block); if (!el) return;
         el.scrollIntoView({ block: "center" }); el.classList.add("flash-block");
         setTimeout(function () { el.classList.remove("flash-block"); }, 1600);
         el.tabIndex = -1; el.focus({ preventScroll: true });
       }],
       ["Remove", function () {
         clips = (stored ? loadClips() : clips).filter(function (x) { return x.id !== c.id; });
         if (stored) stored = save(CLIP_KEY, clips);
         renderClips(); clipsBtn.focus();
       }]
      ].forEach(function (x) {
        var b = document.createElement("button"); b.type = "button"; b.textContent = x[0];
        b.setAttribute("aria-label", x[0] + " quote " + (i + 1));
        b.addEventListener("click", function (e) { e.stopPropagation(); x[1](); });
        acts.appendChild(b);
      });
      li.appendChild(q); li.appendChild(m); li.appendChild(acts); ol.appendChild(li);
    });
    clipsPanel.appendChild(ol);
  }
  function setClips(open, refocus) {
    if (!clipsPanel) return;
    if (open) { setPanel(false); if (stored) clips = loadClips(); renderClips(); }
    clipsPanel.hidden = !open;
    clipsBtn.setAttribute("aria-expanded", String(open));
    if (open) { var f = clipsPanel.querySelector("button"); if (f) f.focus(); }
    if (!open && refocus) clipsBtn.focus();
  }
  if (clipsBtn && clipsPanel) {
    renderClips();
    clipsBtn.addEventListener("click", function (e) { e.stopPropagation(); setClips(clipsPanel.hidden); });
    document.addEventListener("click", function (e) { if (!clipsPanel.hidden && !clipsPanel.contains(e.target)) setClips(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !clipsPanel.hidden) setClips(false, true); });
    if (aa) aa.addEventListener("click", function () { if (!clipsPanel.hidden) setClips(false); });
  }
  function checkSelection() {
    var sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) { hideSave(); return; }
    var range = sel.getRangeAt(0);
    var main = document.querySelector("main");
    var anc = range.commonAncestorContainer;
    if (!main || !main.contains(anc) || (anc.nodeType === 1 ? anc : anc.parentNode).closest("header.paper, .references, .clip-save, footer, .done-box, .orig-page")) { hideSave(); return; }
    var text = quoteText(range);
    if (text.length < 3) { hideSave(); return; }
    pending = locate(range); pending.text = text;
    if (!saveBtn) {
      saveBtn = document.createElement("button");
      saveBtn.type = "button"; saveBtn.className = "clip-save"; saveBtn.textContent = "Save quote";
      saveBtn.addEventListener("mousedown", function (e) { e.preventDefault(); });  // keep the selection
      saveBtn.addEventListener("click", function (e) { e.stopPropagation(); saveClip(); });
      document.body.appendChild(saveBtn);
    }
    var r = range.getBoundingClientRect();
    var top = window.scrollY + r.top - saveBtn.offsetHeight - 8;
    if (r.top - saveBtn.offsetHeight - 8 < 56) top = window.scrollY + r.bottom + 8;
    var left = Math.min(window.scrollX + r.left + r.width / 2 - saveBtn.offsetWidth / 2, window.scrollX + document.documentElement.clientWidth - saveBtn.offsetWidth - 12);
    saveBtn.style.top = top + "px"; saveBtn.style.left = Math.max(8, left) + "px";
  }
  var selTimer = null;
  if (clipsBtn) document.addEventListener("selectionchange", function () { clearTimeout(selTimer); selTimer = setTimeout(checkSelection, 150); });
  if (clipsBtn) document.addEventListener("keydown", function (e) {
    var tag = (e.target.tagName || "").toLowerCase();
    if ((e.key === "q" || e.key === "Q") && !e.metaKey && !e.ctrlKey && !e.altKey && tag !== "input" && tag !== "textarea" && !e.target.isContentEditable) {
      checkSelection();  // the selection may have changed in the last moment
      if (pending) { e.preventDefault(); saveClip(); }
    }
    if (e.key === "Escape") hideSave();
  });

  /* ---------- figures: click to widen ---------- */
  document.addEventListener("click", function (e) {
    var img = e.target.closest("figure img"); if (!img) return;
    img.closest("figure").classList.toggle("wide");
  });

  /* ---------- position, progress and time left ---------- */
  var blocks = [].slice.call(document.querySelectorAll("main [data-w]"));
  var heads = [].slice.call(document.querySelectorAll("main [data-sec]"));
  var tocLinks = {};
  document.querySelectorAll("nav.toc a[href^='#']").forEach(function (a) { tocLinks[a.getAttribute("href").slice(1)] = a; });
  var bodyEndEl = document.getElementById("end-of-body");
  var where = document.getElementById("where");
  var bar = document.getElementById("progress");
  var geo = [];

  function measure() {
    geo = blocks.map(function (b) {
      return { el: b, top: b.getBoundingClientRect().top + window.scrollY, w: +b.getAttribute("data-w"), sec: b.getAttribute("data-in") || "", body: b.getAttribute("data-body") === "1" };
    });
  }
  function sectionTitle(id) {
    var h = document.getElementById(id); if (!h) return "";
    return h.getAttribute("data-title") || h.textContent;
  }
  var lastSaved = 0, ticking = false, latest = null, saveTimer = null, resumed = false;
  var listed = {}, lastListed = "";  // a section too minor for the contents highlights its parent
  heads.forEach(function (h) { if (tocLinks[h.id]) lastListed = h.id; listed[h.id] = lastListed; });
  function update() {
    ticking = false;
    if (!geo.length) return;
    var y = window.scrollY + Math.max(90, window.innerHeight * 0.3); // a third of the way down, as scroll trackers usually do
    var i = 0; while (i < geo.length - 1 && geo[i + 1].top <= y) i++;
    if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) i = geo.length - 1;  // the end of the page counts as read
    var cur = geo[i];
    var secLeft = 0, bodyLeft = 0, bodyTotal = 0;
    for (var j = 0; j < geo.length; j++) {
      if (geo[j].body) { bodyTotal += geo[j].w; if (j >= i) bodyLeft += geo[j].w; }
      if (j >= i && geo[j].sec === cur.sec) secLeft += geo[j].w;
    }
    var sm = Math.max(1, Math.round(secLeft / WPM)), bm = Math.round(bodyLeft / WPM);
    var atStart = geo[0].top > y;  // still on the title and abstract, before the first section
    if (where && atStart) where.textContent = "About " + Math.max(1, bm) + " min of reading";
    else if (where) {
      var t = sectionTitle(cur.sec);
      where.textContent = !secLeft ? t  // the reference list has no reading time
        : window.innerWidth < 560 ? sm + " min left" + (t ? " · " + t : "")
        : (t ? t + " · " : "") + "about " + sm + " min left in section" + (cur.body && bm ? " · " + bm + " min to the end of the main text" : "");
    }
    if (bar && bodyTotal) bar.style.width = (100 * (1 - bodyLeft / bodyTotal)) + "%";
    Object.keys(tocLinks).forEach(function (k) { var on = !atStart && k === (listed[cur.sec] || cur.sec);
      tocLinks[k].classList.toggle("current", on);
      if (on) tocLinks[k].setAttribute("aria-current", "location"); else tocLinks[k].removeAttribute("aria-current"); });
    latest = { id: cur.el.id, started: bodyTotal && bodyLeft / bodyTotal < 0.97 };
    clearTimeout(saveTimer);
    if (Date.now() - lastSaved > 1500) savePosition();
    else saveTimer = setTimeout(savePosition, 1500);  // so the place where scrolling stops is the one kept
  }
  function savePosition() {
    if (!latest || !resumed) return;  // nothing is saved until the saved place has been restored
    lastSaved = Date.now();
    var st = load("litreader.status." + pid, {});
    st.pos = latest.id; st.at = new Date().toISOString();
    if (!st.state && latest.started) st.state = "started";
    save("litreader.status." + pid, st);
  }
  window.addEventListener("pagehide", savePosition);
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  window.addEventListener("resize", function () { measure(); update(); });

  var live = document.createElement("div");  // present before it speaks, so screen readers announce the change
  live.className = "sr"; live.setAttribute("role", "status");
  document.body.appendChild(live);
  function toast(html, ms) {
    var t = document.createElement("div"); t.className = "toast"; t.innerHTML = html;
    document.body.appendChild(t); setTimeout(function () { t.remove(); }, ms || 5000);
    setTimeout(function () { live.textContent = t.firstChild.textContent; }, 100);
    return t;
  }

  /* ---------- long author lists ---------- */
  var auToggle = document.getElementById("au-toggle");
  var auRest = document.getElementById("au-rest");
  if (auToggle && auRest) auToggle.addEventListener("click", function () {
    var open = auToggle.getAttribute("aria-expanded") !== "true";
    auToggle.setAttribute("aria-expanded", String(open));
    auRest.hidden = !open;
    auToggle.querySelector(".au-label").textContent = open ? "Show fewer" : auToggle.getAttribute("data-more");
    measure(); update();
  });

  /* ---------- finished marker ---------- */
  var doneBtn = document.getElementById("mark-done");
  function showDone() {
    var st = load("litreader.status." + pid, {});
    if (doneBtn) doneBtn.textContent = st.state === "done" ? "Finished ✓ (click to undo)" : "Mark as finished";
  }
  if (doneBtn) doneBtn.addEventListener("click", function () {
    var st = load("litreader.status." + pid, {});
    st.state = st.state === "done" ? "started" : "done"; save("litreader.status." + pid, st); showDone();
  });

  function start() {
    measure(); showDone();
    var st = load("litreader.status." + pid, {});
    if (!location.hash && st.pos && st.pos !== (blocks[0] && blocks[0].id)) {
      var el = document.getElementById(st.pos);
      if (el) {
        window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - Math.max(90, window.innerHeight * 0.3) + 1);  // back on the line position is read from
        el.classList.add("flash-block");
        var t = toast("Resumed where you left off. <button type='button'>Back to the start</button>", 8000);
        t.querySelector("button").addEventListener("click", function () { window.scrollTo(0, 0); t.remove(); });
      }
    }
    resumed = true;
    update();
  }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(start); else window.addEventListener("load", start);
  window.addEventListener("load", function () { measure(); update(); });
  if (window.ResizeObserver) {  // images and fonts move the text after the first measurement
    var layoutTimer = null;
    new ResizeObserver(function () {
      clearTimeout(layoutTimer);
      layoutTimer = setTimeout(function () { measure(); update(); }, 120);
    }).observe(document.querySelector("main"));
  }
})();
