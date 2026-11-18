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
  function save(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {} }

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
  if (aa && panel) {
    aa.addEventListener("click", function (e) { e.stopPropagation(); panel.hidden = !panel.hidden; });
    document.addEventListener("click", function (e) { if (!panel.hidden && !panel.contains(e.target)) panel.hidden = true; });
    panel.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      if (b.hasAttribute("data-pref")) prefs[b.getAttribute("data-pref")] = b.getAttribute("data-val");
      if (b.id === "size-down" || b.id === "size-up") {
        var i = SIZES.indexOf(prefs.size || 20); if (i < 0) i = 4;
        i = Math.max(0, Math.min(SIZES.length - 1, i + (b.id === "size-up" ? 1 : -1)));
        prefs.size = SIZES[i];
      }
      save(PREF_KEY, prefs); applyPrefs();
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
  if (tocToggle && toc) {
    tocToggle.addEventListener("click", function (e) { e.stopPropagation(); toc.classList.toggle("open"); });
    toc.addEventListener("click", function (e) { if (e.target.closest("a")) toc.classList.remove("open"); });
  }

  /* ---------- sidenotes on narrow screens ---------- */
  document.addEventListener("click", function (e) {
    var m = e.target.closest(".sn-mark"); if (!m) return;
    var n = document.getElementById(m.getAttribute("data-for"));
    if (n && getComputedStyle(n).float === "none") n.classList.toggle("open");
  });

  /* ---------- citation cards ---------- */
  var card = null;
  function closeCard() { if (card) { card.remove(); card = null; } }
  function openCard(a) {
    closeCard();
    var ids = (a.getAttribute("data-ref") || "").split(" ").filter(Boolean);
    if (!ids.length) return;
    card = document.createElement("div");
    card.className = "cite-card";
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
      });
      d.appendChild(go);
      card.appendChild(d);
    });
    if (!card.childNodes.length) { card = null; return; }
    document.body.appendChild(card);
    var r = a.getBoundingClientRect();
    var top = window.scrollY + r.bottom + 6;
    var left = Math.min(window.scrollX + r.left, window.scrollX + document.documentElement.clientWidth - card.offsetWidth - 12);
    card.style.top = top + "px"; card.style.left = Math.max(8, left) + "px";
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
    if (a) { e.preventDefault(); openCard(a); return; }
    if (card && !card.contains(e.target)) closeCard();
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { closeCard(); if (panel) panel.hidden = true; } });

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
  var lastSaved = 0, ticking = false;
  function update() {
    ticking = false;
    if (!geo.length) return;
    var y = window.scrollY + Math.max(90, window.innerHeight * 0.3); // a third of the way down, as scroll trackers usually do
    var i = 0; while (i < geo.length - 1 && geo[i + 1].top <= y) i++;
    var cur = geo[i];
    var secLeft = 0, bodyLeft = 0, bodyTotal = 0;
    for (var j = 0; j < geo.length; j++) {
      if (geo[j].body) { bodyTotal += geo[j].w; if (j >= i) bodyLeft += geo[j].w; }
      if (j >= i && geo[j].sec === cur.sec) secLeft += geo[j].w;
    }
    var sm = Math.max(1, Math.round(secLeft / WPM)), bm = Math.round(bodyLeft / WPM);
    if (where) {
      var t = sectionTitle(cur.sec);
      where.textContent = (t ? t + " · " : "") + "about " + sm + " min left in section" +
        (cur.body ? " · " + bm + " min to the end of the main text" : "");
    }
    if (bar && bodyTotal) bar.style.width = (100 * (1 - bodyLeft / bodyTotal)) + "%";
    Object.keys(tocLinks).forEach(function (k) { tocLinks[k].classList.toggle("current", k === cur.sec); });
    var now = Date.now();
    if (now - lastSaved > 1500) {
      lastSaved = now;
      var st = load("litreader.status." + pid, {});
      st.pos = cur.el.id; st.at = new Date().toISOString();
      if (!st.state && bodyTotal && bodyLeft / bodyTotal < 0.97) st.state = "started";
      save("litreader.status." + pid, st);
    }
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  window.addEventListener("resize", function () { measure(); update(); });

  function toast(html, ms) {
    var t = document.createElement("div"); t.className = "toast"; t.innerHTML = html;
    document.body.appendChild(t); setTimeout(function () { t.remove(); }, ms || 5000); return t;
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
        el.scrollIntoView({ block: "start" });
        el.classList.add("flash-block");
        var t = toast("Resumed where you left off. <button type='button'>Back to the start</button>", 6000);
        t.querySelector("button").addEventListener("click", function () { window.scrollTo(0, 0); t.remove(); });
      }
    }
    update();
  }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(start); else window.addEventListener("load", start);
  window.addEventListener("load", function () { measure(); update(); });
})();
