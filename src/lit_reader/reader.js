/* lit_reader: reading controls. No network access, no dependencies.
   Stores preferences, reading position and status in localStorage,
   wrapped in try/catch so the page still works when storage is blocked. */
(function () {
  "use strict";
  window.litReaderRan = true;  // the page's flag script checks this: without it, the no-script fallbacks show
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
  var phone = window.matchMedia && matchMedia("(max-width: 600px)").matches;
  var touch = window.matchMedia && matchMedia("(pointer: coarse)").matches;
  var DEFAULT_SIZE = phone ? 18 : 20;  // about 40 characters a line on a phone, rather than 35
  var wideQuery = window.matchMedia ? matchMedia("(min-width: 981px)") : { matches: true };
  function focusQuietly(el, byPointer) {  // focus follows a jump, but a tap or click doesn't leave a ring behind
    el.focus({ preventScroll: true });
    if (byPointer && document.activeElement === el) {  // only once focus has landed, or the ring could stay hidden for good
      el.classList.add("quiet-focus");
      el.addEventListener("blur", function () { el.classList.remove("quiet-focus"); }, { once: true });
    }
  }
  function home(btn) {  // on a phone the bar's Quotes and Aa are hidden: focus goes back to the contents button
    if (btn && btn.getClientRects().length) return btn;
    return document.getElementById("toc-toggle") || btn || document.body;
  }
  function barBottom() { var b = document.querySelector(".bar"); return (b ? b.offsetHeight : 44) + 12; }  // keep clear of the top bar
  var WIDTHS = { narrow: "47ch", medium: "54ch", wide: "62ch" };
  var LHS = { tight: 1.4, normal: 1.5, loose: 1.7 };

  function applyPrefs() {
    if (prefs.theme && prefs.theme !== "auto") root.setAttribute("data-theme", prefs.theme);
    else root.removeAttribute("data-theme");
    if (prefs.font && prefs.font !== "literata") root.setAttribute("data-font", prefs.font);
    else root.removeAttribute("data-font");
    if (prefs.para === "orig") root.setAttribute("data-para", "orig");
    else root.removeAttribute("data-para");
    if (prefs.toc === "hidden") root.setAttribute("data-toc", "hidden");
    else root.removeAttribute("data-toc");
    root.style.setProperty("--size", (prefs.size || DEFAULT_SIZE) + "px");
    root.style.setProperty("--measure", WIDTHS[prefs.width || "medium"]);
    root.style.setProperty("--lh", LHS[prefs.lh || "normal"]);
    document.querySelectorAll(".panel [data-pref]").forEach(function (b) {
      var k = b.getAttribute("data-pref"), v = b.getAttribute("data-val");
      var cur = prefs[k] || { theme: "auto", font: "literata", width: "medium", lh: "normal", para: "short" }[k];
      b.setAttribute("aria-pressed", String(cur === v));
    });
    var sz = document.getElementById("size-now");
    if (sz) sz.textContent = (prefs.size || DEFAULT_SIZE) + "px";
  }
  applyPrefs();

  var panel = document.getElementById("panel");
  var aa = document.getElementById("aa");
  function setPanel(open, refocus) {
    panel.hidden = !open;
    aa.setAttribute("aria-expanded", String(open));
    if (!open && refocus) home(aa).focus();
  }
  if (aa && panel) {
    aa.addEventListener("click", function (e) { e.stopPropagation(); setPanel(panel.hidden); });
    document.addEventListener("click", function (e) { if (!panel.hidden && !panel.contains(e.target)) setPanel(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !panel.hidden) setPanel(false, true); });
    panel.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      if (b.hasAttribute("data-pref")) prefs[b.getAttribute("data-pref")] = b.getAttribute("data-val");
      if (b.id === "size-down" || b.id === "size-up") {
        var i = SIZES.indexOf(prefs.size || DEFAULT_SIZE); if (i < 0) i = 4;
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
    // the index page: each paper's reading status and saved quotes, then every quote together
    var rows = [].slice.call(document.querySelectorAll(".list li[data-pid]"));
    rows.forEach(function (li, n) {
      var st = load("litreader.status." + li.getAttribute("data-pid"), {});
      var s = li.querySelector(".s"); if (!s) return;
      var nq = li.hasAttribute("data-cite") ? indexClips(li.getAttribute("data-pid")).length : 0;
      var share = typeof st.pct === "number" ? st.pct : null;
      var bits = [], when = lastRead(st.readAt);  // only time spent reading: opening or scrolling a paper isn't reading it
      if (st.state === "done") bits.push("Finished");
      else if (share !== null) bits.push(readShare(share));
      else if (st.state) bits.push("In progress");  // opened before read shares were kept
      if (bits.length && when) bits.push("last read " + when);
      if (nq) bits.push(nq === 1 ? "1 quote" : nq + " quotes");
      s.textContent = "";
      bits.forEach(function (b, k) {  // each part kept whole, so a narrow column breaks between them
        if (k) s.appendChild(document.createTextNode(" · "));
        var part = document.createElement("span"); part.className = "part"; part.textContent = b; s.appendChild(part);
      });
      if (bits.length) {
        var a = li.querySelector(".t a");
        s.id = "status-" + n;
        if (a) a.setAttribute("aria-describedby", s.id);  // tabbing to the title also gives its progress
      }
      if (st.state || share !== null) s.className = "s " + (st.state === "done" ? "done" : "started");
      if (share !== null && st.state !== "done") {  // a bar, so the papers can be compared at a glance
        var m = document.createElement("span"); m.className = "meter"; m.setAttribute("aria-hidden", "true");
        var f = document.createElement("span"); f.style.width = Math.round(100 * Math.min(1, Math.max(0, share))) + "%";
        m.appendChild(f); s.appendChild(m);
      }
    });
    var head = document.querySelector("header.paper");
    if (head && rows.some(function (li) { return li.hasAttribute("data-cite"); })) {
      var note = document.createElement("p"); note.className = "progress-note";
      note.textContent = "As you read, each paper here shows how much of its main text you've spent time reading " +
        "(not how far you've scrolled) and when you last read it. “Finished” is your own mark, from the end of each paper.";
      head.appendChild(note);
    }
    indexQuotes(rows);
    return;
  }

  /* How much of the main text has been read, said roughly: the measure is an estimate. */
  function readShare(p) {
    if (p >= 0.999) return "All read";
    var n = Math.round(p * 20) * 5;
    if (n >= 100) n = 95;
    return n < 5 ? "Under 5% read" : "About " + n + "% read";
  }
  /* How long ago, in words, with the date once it is more than a week back:
     "today", "3 days ago", "12 days ago (10 Nov)", "3 weeks ago (1 Nov)", "18 Oct 2025". */
  function lastRead(iso) {
    var d = iso ? new Date(iso) : null;
    if (!d || isNaN(d)) return "";
    var now = new Date(), day = 864e5;
    var days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / day);
    var date = d.toLocaleDateString("en-GB", d.getFullYear() === now.getFullYear() ? { day: "numeric", month: "short" } : { day: "numeric", month: "short", year: "numeric" });
    if (days <= 0) return "today";
    if (days === 1) return "yesterday";
    if (days < 7) return days + " days ago";
    if (days < 14) return days + " days ago (" + date + ")";
    if (days < 60) return Math.floor(days / 7) + " weeks ago (" + date + ")";
    return date;
  }

  function indexClips(p) { var v = load("litreader.clips." + p, []); return Array.isArray(v) ? v : []; }
  /* Every saved quote from the papers on this page, to download or copy as one file.
     Each paper's quotes stay where that paper keeps them; this only reads them. */
  function indexQuotes(rows) {
    var box = document.getElementById("bundle-quotes");
    if (!box) return;
    var seen = {}, papers = [];
    rows.forEach(function (li) {
      var p = li.getAttribute("data-pid");
      if (seen[p] || !li.hasAttribute("data-cite")) return;  // a paper listed twice keeps one set of quotes
      seen[p] = true;
      var c = indexClips(p);
      if (c.length) papers.push({ pid: p, clips: c, title: li.getAttribute("data-title") || "",
                                  cite: li.getAttribute("data-cite") || "", reference: li.getAttribute("data-reference") || "" });
    });
    if (!papers.length) return;
    var heading = (document.querySelector("h1") || {}).textContent || "these papers";
    var status = document.createElement("p"); status.className = "sr"; status.setAttribute("role", "status");
    function exportedKey(pp) { return "litreader.clipsExported." + pp.pid; }
    function notExported(pp) { var at = load(exportedKey(pp), ""); return pp.clips.filter(function (c) { return !at || c.at > at; }).length; }
    function citeFor(pp, c) { return "(" + pp.cite + (c.page ? (c.page.indexOf("–") > 0 ? ", pp. " : ", p. ") + c.page : "") + ")"; }
    function markdown() {
      var out = ["# Quotes from " + heading, ""];
      papers.forEach(function (pp) {
        out.push("## " + pp.title, "", pp.reference, "");
        pp.clips.forEach(function (c) { out.push("> " + c.text, "", citeFor(pp, c) + (c.sec ? " · " + c.sec : ""), ""); });
      });
      return out.join("\n");
    }
    function markExported(label) {
      var now = new Date().toISOString();
      papers.forEach(function (pp) { save(exportedKey(pp), now); });  // each paper's own reminder clears too
      draw();
      var b = [].filter.call(box.querySelectorAll("button"), function (x) { return x.textContent === label; })[0];
      if (b) b.focus();  // the clicked button was redrawn
    }
    function download() {
      var a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([markdown()], { type: "text/markdown" }));
      a.download = "quotes-" + (heading.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "papers") + ".md";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
      markExported("Download as Markdown");
    }
    function copyAll() {
      var text = markdown();
      function fallback() {
        var t = document.createElement("textarea"), ok = false; t.value = text; t.setAttribute("readonly", "");
        t.style.position = "fixed"; t.style.opacity = "0"; document.body.appendChild(t); t.select();
        try { ok = document.execCommand("copy"); } catch (e) {}
        t.remove();
        return ok;
      }
      function done(ok) {
        if (ok) markExported("Copy all");
        status.textContent = ok ? "Copied." : "Couldn't copy. Use Download as Markdown instead.";
        if (!box.contains(status)) box.appendChild(status);
      }
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(fallback()); });
      else done(fallback());
    }
    function draw() {
      box.innerHTML = "";
      box.hidden = false;
      var total = 0, left = 0;
      papers.forEach(function (pp) { total += pp.clips.length; left += notExported(pp); });
      var h = document.createElement("h2"); h.id = "bundle-quotes-h"; h.textContent = "Saved quotes";
      var p = document.createElement("p"); p.className = "listnote";
      p.textContent = (total === 1 ? "1 quote" : total + " quotes") + " from " + (papers.length === 1 ? "1 paper" : papers.length + " papers") +
        ", kept only in this browser. " + (!left ? "All downloaded." : left === total ? "None downloaded yet." : left + " not downloaded yet.") +
        " The file groups them by paper, each with its citation.";
      var row = document.createElement("div"); row.className = "row";
      [["Download as Markdown", download], ["Copy all", copyAll]].forEach(function (x, i) {
        var b = document.createElement("button"); b.type = "button"; b.textContent = x[0];
        if (i === 0) b.className = "primary";
        b.addEventListener("click", x[1]); row.appendChild(b);
      });
      box.appendChild(h); box.appendChild(p); box.appendChild(row); box.appendChild(status);
    }
    draw();
  }

  /* ---------- contents: a sidebar that can be put away on wide screens,
     a drawer on narrow ones ---------- */
  var toc = document.querySelector("nav.toc");
  var tocToggle = document.getElementById("toc-toggle");
  function setToc(open, refocus) {
    toc.classList.toggle("open", open);
    tocToggle.setAttribute("aria-expanded", String(open));
    if (open) { var first = toc.querySelector("a"); if (first) setTimeout(function () { first.focus(); }, 30); }
    if (!open && refocus) tocToggle.focus();
  }
  function syncToc() {  // the button says whether the contents are showing at this width
    if (wideQuery.matches) { toc.classList.remove("open"); tocToggle.setAttribute("aria-expanded", String(prefs.toc !== "hidden")); }
    else tocToggle.setAttribute("aria-expanded", String(toc.classList.contains("open")));
  }
  if (tocToggle && toc) {
    syncToc();
    if (wideQuery.addEventListener) wideQuery.addEventListener("change", syncToc);
    tocToggle.addEventListener("click", function (e) {
      e.stopPropagation();
      if (!wideQuery.matches) { setToc(!toc.classList.contains("open")); return; }
      prefs.toc = prefs.toc === "hidden" ? "shown" : "hidden";
      save(PREF_KEY, prefs); applyPrefs(); syncToc();
      measure(); update();
    });
    document.addEventListener("click", function (e) {  // a tap beside the drawer closes it, and does nothing else
      if (toc.classList.contains("open") && !toc.contains(e.target) && e.detail > 0) {  // a key press still does what it was for
        setToc(false); e.preventDefault(); e.stopPropagation();
      }
    }, true);
    toc.addEventListener("click", function (e) {
      var a = e.target.closest("a"); if (!a) return;
      if (!wideQuery.matches) setToc(false);
      var to = a.hash && document.getElementById(a.hash.slice(1));  // keyboard focus moves with the jump
      if (to) { to.tabIndex = -1; setTimeout(function () { focusQuietly(to, e.detail > 0); }, 30); }
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && toc.classList.contains("open")) setToc(false, true); });
    toc.querySelectorAll("[data-proxy]").forEach(function (b) {  // Quotes and Aa, kept in the drawer on a phone
      b.addEventListener("click", function (e) {
        e.stopPropagation();  // or the click would reach the page and close the panel it opens
        var real = document.getElementById(b.getAttribute("data-proxy"));
        setToc(false);
        if (real) real.click();
        var opened = real && document.getElementById(real.getAttribute("aria-controls") || "panel");
        if (real && real.id === "aa" && opened && !opened.hidden) {  // Quotes moves focus itself; settings would leave it in the closed drawer
          var first = opened.querySelector("button, input, select, a[href]"); if (first) first.focus();
        }
      });
    });
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
  function offerWayBack(li, from, fromY) {  // a button under the reference, back to the citation it came from
    document.querySelectorAll(".ref-back").forEach(function (b) { b.remove(); });
    var b = document.createElement("button");
    b.type = "button"; b.className = "ref-back"; b.textContent = "↩ Back to where you were";
    b.addEventListener("click", function (e) {
      e.stopPropagation(); b.remove();
      if (from && from.getClientRects().length) from.scrollIntoView({ block: "center" });  // the citation itself: right even after the text size changed
      else window.scrollTo(0, fromY);
      if (from) focusQuietly(from, e.detail > 0);
    });
    li.appendChild(b);
  }
  function goToRef(li, byPointer) {  // the default jump to #ref-… happens after, from the link itself
    var from = cardFrom, fromY = window.scrollY;
    closeCard(); li.classList.add("flash"); setTimeout(function () { li.classList.remove("flash"); }, 1600);
    var det = li.closest("details"); if (det) det.open = true;
    offerWayBack(li, from, fromY);
    li.tabIndex = -1; setTimeout(function () { focusQuietly(li, byPointer); }, 30);
  }
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
      d.querySelectorAll(".ref-back").forEach(function (b) { b.remove(); });
      var go = document.createElement("a");
      go.href = "#ref-" + id; go.className = "go"; go.textContent = "Go to reference list";
      go.addEventListener("click", function (e) { goToRef(li, e.detail > 0); });
      d.appendChild(go);
      card.appendChild(d);
    });
    if (!card.childNodes.length) { card = null; return; }
    document.body.appendChild(card);
    var r = a.getBoundingClientRect();
    var top = window.scrollY + r.bottom + 6;
    if (r.bottom + 6 + card.offsetHeight > window.innerHeight) top = Math.max(window.scrollY + barBottom(), window.scrollY + r.top - card.offsetHeight - 6);
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
    if (touch) return;  // a tap sends a mouseover too; the click opens the card
    var a = e.target.closest && e.target.closest("a.cite");
    if (a) { clearTimeout(hoverTimer); hoverTimer = setTimeout(function () { openCard(a); }, 250); }
  });
  document.addEventListener("mouseout", function (e) {
    var a = e.target.closest && e.target.closest("a.cite");
    if (a) clearTimeout(hoverTimer);
  });
  document.addEventListener("click", function (e) {
    var a = e.target.closest("a.cite");
    if (a && !touch && card && cardFrom === a && e.detail > 0) {  // hovering already opened its card: a click goes on to the reference
      var go = card.querySelector("a.go"), li = go && document.getElementById(go.getAttribute("href").slice(1));
      if (li) { e.preventDefault(); goToRef(li, true);
        if (location.hash === "#" + li.id) li.scrollIntoView(); else location.hash = li.id;  // as the card's own link does
        return; }
    }
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
  var removed = null;  // the last quote removed, offered back until the panel closes

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
  function copy(text, then) {
    function fallback() {
      var t = document.createElement("textarea"), ok = false; t.value = text; t.setAttribute("readonly", "");
      t.style.position = "fixed"; t.style.opacity = "0"; document.body.appendChild(t); t.select();
      try { ok = document.execCommand("copy"); } catch (e) {}
      t.remove();
      return ok;
    }
    function done(ok) { if (ok && then) then(); toast(ok ? "<span>Copied.</span>" : "<span>Couldn't copy. Use Download as Markdown instead.</span>", ok ? 2500 : 5000); }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(fallback()); });
    else done(fallback());
  }
  var EXPORTED_KEY = "litreader.clipsExported." + pid;  // when this paper's quotes were last downloaded or copied
  var exportedAt = "";  // also kept here, for a browser that won't store it
  function notExported() {
    var at = load(EXPORTED_KEY, "") || exportedAt;
    return clips.filter(function (c) { return !at || c.at > at; }).length;
  }
  function markExported() {
    exportedAt = new Date().toISOString(); save(EXPORTED_KEY, exportedAt);
    var open = clipsPanel && !clipsPanel.hidden, from = document.activeElement, label = from && from.textContent;
    var inDone = doneQuotes && doneQuotes.contains(from);
    renderClips();
    if (open && !inDone) {  // the clicked button was redrawn: back to the same one
      var b = [].filter.call(clipsPanel.querySelectorAll(".row button"), function (x) { return x.textContent === label; })[0];
      if (b) b.focus();
    }
    if (inDone && doneBtn) doneBtn.focus();  // the reminder and its button are gone
  }
  function download() {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([asMarkdown()], { type: "text/markdown" }));
    a.download = "quotes-" + (document.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40) || "paper") + ".md";
    a.addEventListener("click", function (e) { e.stopPropagation(); });  // not a click outside the Quotes panel
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
    markExported();
  }
  function quotesWord(n) { return n === 1 ? "1 quote" : n + " quotes"; }
  // At the end of the main text: a reminder, only when there are quotes not yet downloaded.
  var doneQuotes = null;
  function showDoneQuotes() {
    var box = document.querySelector(".done-box");
    if (!box) return;
    var n = notExported();
    if (!n) { if (doneQuotes) { doneQuotes.remove(); doneQuotes = null; } return; }
    if (!doneQuotes) {
      doneQuotes = document.createElement("p"); doneQuotes.className = "done-quotes";
      var s = document.createElement("span"), b = document.createElement("button");
      b.type = "button"; b.textContent = "Download";
      b.addEventListener("click", download);
      doneQuotes.appendChild(s); doneQuotes.appendChild(document.createTextNode(" ")); doneQuotes.appendChild(b);
      box.appendChild(doneQuotes);
    }
    doneQuotes.firstChild.textContent = "You saved " + quotesWord(n) + " from this paper that you haven't downloaded. " + (
      !stored ? "This browser isn't keeping " + (n === 1 ? "it" : "them") + ": " + (n === 1 ? "it goes" : "they go") + " when you close this tab."
              : (n === 1 ? "It's" : "They're") + " kept only in this browser.");
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
    var first = !load(HINT_KEY, {}).saved;
    save(HINT_KEY, { done: true, saved: true });  // they know about quotes now: no more tips
    var n = notExported();
    toast(!stored ? "<span>This browser won't keep quotes for local pages, so they last only until you close this tab. Open Quotes to copy or download them now.</span>"
          : first ? "<span>Quote saved in this browser. Open Quotes in the top bar to copy it with its citation, or download your quotes as a file to keep.</span>"
          : n >= 3 ? "<span>Quote saved. " + quotesWord(n) + " from this paper aren't downloaded yet. Open Quotes to download them.</span>"
          : "<span>Quote saved.</span>", stored ? (first || n >= 3 ? 6000 : 2500) : 9000);
  }
  /* A tip, on the first few papers someone scrolls through, that passages can be saved.
     Selecting text is the only way in, and nothing on the page shows it otherwise. */
  var HINT_KEY = "litreader.quoteHint", hintChecked = false;
  function maybeHint() {
    if (hintChecked || !clipsBtn || !hintReady || window.scrollY < window.innerHeight * 1.5) return;
    if (document.querySelector(".toast")) return;  // after "Resumed where you left off", not instead of it
    hintChecked = true;
    var h = load(HINT_KEY, {}), seen = Array.isArray(h.papers) ? h.papers : [];
    if (h.done || clips.length || seen.indexOf(pid) >= 0 || seen.length >= 3) return;
    seen.push(pid); save(HINT_KEY, { papers: seen });
    var t = toast(touch ? "<span>Tip: press and hold on a passage to select it, then tap Save quote. It keeps the page and citation.</span> <button type=\"button\">Got it</button>"
                        : "<span>Tip: select a passage and press Q, or choose Save quote, to keep it with its page and citation.</span> <button type=\"button\">Got it</button>", 12000);
    t.querySelector("button").addEventListener("click", function () { save(HINT_KEY, { done: true }); t.remove(); });
  }
  var hintReady = false;  // the jump back to a saved position isn't the reader scrolling
  setTimeout(function () { hintReady = true; }, 2000);
  if (clipsBtn) window.addEventListener("scroll", maybeHint, { passive: true });
  function renderClips() {
    if (clipCount) clipCount.textContent = clips.length ? "(" + clips.length + ")" : "";
    document.querySelectorAll(".clip-count-n").forEach(function (n) { n.textContent = clips.length ? " (" + clips.length + ")" : ""; });
    showDoneQuotes();
    if (!clipsPanel) return;
    clipsPanel.innerHTML = "";
    var h = document.createElement("div"); h.className = "clips-head";
    h.textContent = clips.length ? "Saved quotes" : "No saved quotes yet";
    clipsPanel.appendChild(h);
    if (!clips.length && !removed) {
      var p = document.createElement("p"); p.className = "note";
      p.textContent = touch ? "Select text in the paper, then tap Save quote. Quotes stay in this browser."
                            : "Select text in the paper, then choose Save quote or press Q. Quotes stay in this browser.";
      clipsPanel.appendChild(p);
      return;
    }
    if (clips.length) {
      var n = notExported(), kept = document.createElement("p"); kept.className = "note clips-kept";
      kept.textContent = !stored ? "This browser isn't keeping these: they go when you close this tab. Download them to keep them."
                       : n ? "These are kept only in this browser. " + (n === clips.length ? "None downloaded yet." : quotesWord(n) + " not downloaded yet.")
                       : "Kept in this browser, and all downloaded.";
      clipsPanel.appendChild(kept);
    }
    var all = document.createElement("div"); all.className = "row";
    if (!clips.length) all.hidden = true;
    [["Download as Markdown", download],
     ["Copy all", function () { copy(asMarkdown(), markExported); }]].forEach(function (x, i) {
      var b = document.createElement("button"); b.type = "button"; b.textContent = x[0];
      if (i === 0) b.className = "primary";
      b.addEventListener("click", function (e) { e.stopPropagation(); x[1](); }); all.appendChild(b);
    });
    clipsPanel.appendChild(all);
    var ol = document.createElement("ol"); ol.className = "clips";
    function undoItem() {  // above the list, so the quotes' numbers still match their place in it
      var li = document.createElement("div"); li.className = "clip-removed";
      var s = document.createElement("span"); s.textContent = "Quote removed.";
      var b = document.createElement("button"); b.type = "button"; b.textContent = "Undo";
      b.setAttribute("aria-label", "Undo removing the quote");
      b.addEventListener("click", function (e) {
        e.stopPropagation();
        if (stored) clips = loadClips();
        clips.splice(Math.min(removed.at, clips.length), 0, removed.clip);
        if (stored) stored = save(CLIP_KEY, clips);
        var id = removed.clip.id; removed = null;
        renderClips();
        var back = clipsPanel.querySelector('li[data-id="' + id + '"] button');
        if (back) back.focus(); else home(clipsBtn).focus();
      });
      li.appendChild(s); li.appendChild(b);
      return li;
    }
    if (removed) clipsPanel.appendChild(undoItem());
    clips.forEach(function (c, i) {
      var li = document.createElement("li");
      li.setAttribute("data-id", c.id);
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
         removed = { clip: c, at: i };
         clips = (stored ? loadClips() : clips).filter(function (x) { return x.id !== c.id; });
         if (stored) stored = save(CLIP_KEY, clips);
         renderClips();
         var u = clipsPanel.querySelector(".clip-removed button");
         if (u) u.focus(); else home(clipsBtn).focus();
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
    if (!open) removed = null;
    clipsPanel.hidden = !open;
    clipsBtn.setAttribute("aria-expanded", String(open));
    if (open) { var f = clipsPanel.querySelector("button"); if (f) f.focus(); }
    if (!open && refocus) home(clipsBtn).focus();
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
    if (!main || !main.contains(anc) || (anc.nodeType === 1 ? anc : anc.parentNode).closest("header.paper, .references, .clip-save, footer, .done-box, .orig-page, .table-text")) { hideSave(); return; }
    var text = quoteText(range);
    if (text.length < 3) { hideSave(); return; }
    pending = locate(range); pending.text = text;
    if (!saveBtn) {
      saveBtn = document.createElement("button");
      saveBtn.type = "button"; saveBtn.className = "clip-save"; saveBtn.textContent = "Save quote";
      if (!touch) { saveBtn.setAttribute("aria-keyshortcuts", "Q"); saveBtn.title = "Save quote (Q)"; }
      saveBtn.addEventListener("mousedown", function (e) { e.preventDefault(); });  // keep the selection
      saveBtn.addEventListener("click", function (e) { e.stopPropagation(); saveClip(); });
      document.body.appendChild(saveBtn);
    }
    var r = range.getBoundingClientRect();
    var top = window.scrollY + r.top - saveBtn.offsetHeight - 8;
    if (touch) {  // a phone puts its own copy menu above the selection: go below, past the drag handle
      top = window.scrollY + r.bottom + 30;
      if (r.bottom + 30 + saveBtn.offsetHeight > window.innerHeight - 8) top = window.scrollY + Math.max(barBottom(), r.top - saveBtn.offsetHeight - 56);
    } else if (r.top - saveBtn.offsetHeight - 8 < barBottom()) top = window.scrollY + r.bottom + 8;
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

  /* ---------- figures: each image is a button. With a margin to spread
     into, it widens the figure in place; on narrower screens it opens the
     figure full screen, at a size where its text can be read. ---------- */
  var marginQuery = window.matchMedia ? matchMedia("(min-width: 1261px)") : { matches: true };
  var figBtns = [];
  function figName(fig) {
    var l = fig.querySelector("figcaption .label");
    var img = fig.querySelector("img"), kind = img && /^Table\b/.test(img.alt) ? "Table" : "Figure";  // an unlabelled table is still a table
    return (l ? l.textContent : "").replace(/[.:]\s*$/, "").trim() || kind;
  }
  document.querySelectorAll("main figure img").forEach(function (img) {
    if (img.closest("figcaption, .tablewrap, table")) return;  // an equation in a caption or cell is not the figure
    var b = document.createElement("button");
    b.type = "button"; b.className = "fig-zoom";
    img.parentNode.insertBefore(b, img); b.appendChild(img);
    figBtns.push(b);
  });
  function syncFigs() {
    figBtns.forEach(function (b) {
      var fig = b.closest("figure"), what = b.querySelector("img").alt || figName(fig);  // arXiv's figures often have no alt
      if (marginQuery.matches) {
        b.removeAttribute("aria-haspopup"); b.setAttribute("aria-pressed", String(fig.classList.contains("wide")));
        b.setAttribute("aria-label", what + " (widen into the margin)");
      } else {
        fig.classList.remove("wide"); b.removeAttribute("aria-pressed"); b.setAttribute("aria-haspopup", "dialog");
        b.setAttribute("aria-label", what + " (open full screen)");
      }
    });
  }
  syncFigs();
  if (marginQuery.addEventListener) marginQuery.addEventListener("change", syncFigs);

  var viewer = null, viewerFrom = null, viewerByPointer = false;
  var behind = [];
  function closeViewer() {
    if (!viewer) return;
    viewer.remove(); viewer = null;
    behind.forEach(function (el) { el.inert = false; });
    behind = [];
    root.style.overflow = "";
    if (viewerFrom) focusQuietly(viewerFrom, viewerByPointer);
  }
  function openViewer(b, byPointer) {
    var img = b.querySelector("img"), name = figName(b.closest("figure"));
    setPanel(false); setClips(false); closeCard();
    viewerFrom = b; viewerByPointer = byPointer;
    viewer = document.createElement("div"); viewer.className = "viewer";
    viewer.setAttribute("role", "dialog"); viewer.setAttribute("aria-modal", "true"); viewer.setAttribute("aria-label", name);
    var head = document.createElement("div"); head.className = "viewer-bar";
    var title = document.createElement("span"); title.className = "viewer-title"; title.textContent = name;
    var size = document.createElement("button"); size.type = "button";
    var close = document.createElement("button"); close.type = "button"; close.textContent = "Close";
    head.appendChild(title); head.appendChild(size); head.appendChild(close);
    var body = document.createElement("div"); body.className = "viewer-body"; body.tabIndex = 0;
    body.setAttribute("role", "region"); body.setAttribute("aria-label", name + ", scrolls both ways");
    var big = document.createElement("img"); big.src = img.src; big.alt = img.alt;
    body.appendChild(big);
    viewer.appendChild(head); viewer.appendChild(body);
    document.body.appendChild(viewer);
    behind = [].filter.call(document.body.children, function (el) { return el !== viewer && !el.inert; });  // everything else, toasts and the skip link too
    behind.forEach(function (el) { el.inert = true; });
    root.style.overflow = "hidden";
    var natural = img.naturalWidth || +img.getAttribute("width") || 0;
    var room = body.clientWidth - 24;
    function setFull(on) {
      viewer.classList.toggle("full", on);
      big.style.width = on ? Math.min(natural, room * 3) + "px" : "";
      size.textContent = on ? "Fit to screen" : "Full size";
    }
    if (natural > room * 1.2) setFull(true);  // big enough that the full size is worth having: start there
    else { setFull(false); size.hidden = true; }
    size.addEventListener("click", function () { setFull(!viewer.classList.contains("full")); });
    close.addEventListener("click", closeViewer);
    viewer.addEventListener("keydown", function (e) { if (e.key === "Escape") { e.stopPropagation(); closeViewer(); } });
    close.focus();
  }
  document.addEventListener("keydown", function (e) { if (viewer && e.key === "Escape") closeViewer(); });  // also when focus has dropped to the page
  document.addEventListener("click", function (e) {
    var b = e.target.closest(".fig-zoom"); if (!b) return;
    if (marginQuery.matches) {
      var fig = b.closest("figure");
      b.setAttribute("aria-pressed", String(fig.classList.toggle("wide")));
    } else openViewer(b, e.detail > 0);
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
      var r = b.getBoundingClientRect();
      return { el: b, top: r.top + window.scrollY, bottom: r.bottom + window.scrollY, w: +b.getAttribute("data-w"), sec: b.getAttribute("data-in") || "", body: b.getAttribute("data-body") === "1" };
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
        : window.innerWidth < 560 ? sm + " min left in section" + (t ? " · " + t : "")
        : (t ? t + " · " : "") + "about " + sm + " min left in section" + (cur.body && bm ? " · " + bm + " min to the end of the main text" : "");
    }
    if (bar && bodyTotal) bar.style.width = (100 * (1 - bodyLeft / bodyTotal)) + "%";
    Object.keys(tocLinks).forEach(function (k) { var on = !atStart && k === (listed[cur.sec] || cur.sec);
      tocLinks[k].classList.toggle("current", on);
      if (on) tocLinks[k].setAttribute("aria-current", "location"); else tocLinks[k].removeAttribute("aria-current"); });
    latest = { id: cur.el.id };
    clearTimeout(saveTimer);
    if (Date.now() - lastSaved > 1500) savePosition();
    else saveTimer = setTimeout(savePosition, 1500);  // so the place where scrolling stops is the one kept
  }
  function savePosition() {
    if (!latest || !resumed) return;  // nothing is saved until the saved place has been restored
    lastSaved = Date.now();
    var st = load("litreader.status." + pid, {});
    st.pos = latest.id; st.at = new Date().toISOString();  // where you were, for resuming; a paper counts as started only once something is read
    save("litreader.status." + pid, st);
  }
  window.addEventListener("pagehide", savePosition);

  /* ---------- how much of the main text has been read ----------
     A paragraph counts as read once it has been on screen for as long as it
     takes to read at twice the usual speed. Time on screen goes to the
     paragraphs in view (at least half shown, or filling half the screen)
     from the top down, as you'd read them, so a screen of
     text is not read all at once and skimming past barely counts. The clock
     starts at your first key, touch, click or pointer movement (opening the
     page or resuming your place isn't reading), and stops while the window is
     hidden or in the background, while a figure, the contents drawer or a
     panel covers the text, and after 90 seconds without input. The share is
     saved with the reading status, so the list of papers can show it without
     the page's layout. */
  var READ_WPM = WPM * 2, IDLE_MS = 90 * 1000;
  var readSet = {}, dwell = {}, lastActive = 0;
  (load("litreader.status." + pid, {}).read || []).forEach(function (id) { readSet[id] = true; });
  ["keydown", "pointerdown", "pointermove", "touchstart", "wheel"].forEach(function (t) {  // not "scroll": the page scrolls itself when resuming
    window.addEventListener(t, function () { lastActive = Date.now(); }, { passive: true });
  });
  function saveRead() {
    var st = load("litreader.status." + pid, {});
    (st.read || []).forEach(function (id) { readSet[id] = true; });  // another tab on this paper may have read more
    var bodyTotal = 0, readWords = 0;
    geo.forEach(function (g) { if (g.body) { bodyTotal += g.w; if (readSet[g.el.id]) readWords += g.w; } });
    if (!bodyTotal) return;
    st.read = Object.keys(readSet).filter(function (id) { return document.getElementById(id); });
    st.pct = Math.round(1000 * readWords / bodyTotal) / 1000;
    st.readAt = new Date().toISOString();
    if (!st.state) st.state = "started";
    save("litreader.status." + pid, st);
  }
  setInterval(function () {
    if (!resumed || !geo.length || document.visibilityState !== "visible" || !document.hasFocus() || Date.now() - lastActive > IDLE_MS) return;
    if (viewer || (toc && toc.classList.contains("open")) || (panel && !panel.hidden) || (clipsPanel && !clipsPanel.hidden)) return;  // the text is covered
    var viewTop = window.scrollY + (root.classList.contains("bar-away") ? 0 : barBottom()), viewBottom = window.scrollY + window.innerHeight;
    for (var i = 0; i < geo.length; i++) {
      var g = geo[i];
      if (!g.body || !g.w || readSet[g.el.id]) continue;
      var shown = Math.min(g.bottom, viewBottom) - Math.max(g.top, viewTop);  // a last line peeking out at the top isn't being read
      if (shown <= 0 || (shown < (g.bottom - g.top) / 2 && shown < (viewBottom - viewTop) / 2)) continue;
      dwell[g.el.id] = (dwell[g.el.id] || 0) + 1;
      if (dwell[g.el.id] >= Math.max(2, g.w / READ_WPM * 60)) { readSet[g.el.id] = true; saveRead(); }
      return;  // one paragraph at a time
    }
  }, 1000);
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
  window.addEventListener("resize", function () { measure(); update(); });

  var live = document.createElement("div");  // present before it speaks, so screen readers announce the change
  live.className = "sr"; live.setAttribute("role", "status");
  document.body.appendChild(live);
  function toast(html, ms) {
    document.querySelectorAll(".toast").forEach(function (o) { o.remove(); });  // one at a time: they share a place
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
    if (st.state !== "done") { st.before = st.state || ""; st.state = "done"; }
    else {  // undoing it puts back what the paper showed before
      var before = typeof st.before === "string" ? st.before : (st.pos || (st.read && st.read.length) ? "started" : "");  // marked finished by an earlier version, which kept no "before"
      if (before) st.state = before; else delete st.state;
      delete st.before;
    }
    save("litreader.status." + pid, st); showDone();
    toast(st.state === "done" ? "<span>Marked as finished. It shows on the list of papers.</span>"
                              : "<span>No longer marked as finished.</span>", 3000);
  });

  /* ---------- back to the paper you came from ----------
     Following a reference to another paper of the bundle leaves a note in
     this tab, so that paper's bar can offer the way back to the citation. */
  var FROM_KEY = "litreader.from";
  function fileName(href) { return decodeURIComponent((href || "").split(/[?#]/)[0].split("/").pop()); }
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest(".in-bundle a");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button) return;  // opening elsewhere leaves this tab where it is
    var at = card && card.contains(a) && cardFrom ? cardFrom.closest("main [data-w]") : null;  // the paragraph with the citation
    var block = at ? at.id : (latest && latest.id) || "";
    try { sessionStorage.setItem(FROM_KEY, JSON.stringify({ to: fileName(a.getAttribute("href")), back: fileName(location.pathname),
                                                            block: block, label: cite })); } catch (err) {}
  }, true);
  (function offerWayBack() {
    var from = null;
    try { from = JSON.parse(sessionStorage.getItem(FROM_KEY) || "null"); sessionStorage.removeItem(FROM_KEY); } catch (err) {}
    if (!from || from.to !== fileName(location.pathname) || !from.back || !/^[\w.-]+\.html$/.test(from.back)) return;
    var a = document.createElement("a");
    a.className = "btn back-from";
    a.href = from.back + (from.block && /^[\w-]+$/.test(from.block) ? "#" + from.block : "");
    a.setAttribute("aria-label", "Back to " + (from.label || "the paper you came from"));
    var arrow = document.createElement("span"); arrow.setAttribute("aria-hidden", "true"); arrow.textContent = "↩";
    var lbl = document.createElement("span"); lbl.textContent = " " + (from.label || "Back");
    a.appendChild(arrow); a.appendChild(lbl);
    var bar = document.querySelector(".bar");
    if (bar) bar.insertBefore(a, document.getElementById("toc-toggle"));
  })();

  /* ---------- on a phone, the top bar steps aside while you read on ----------
     Scrolling down hides it; scrolling up, or reaching the top, brings it back.
     Jumps the page makes itself, before you've touched it, don't count. */
  (function barSteppingAside() {
    var phoneNow = window.matchMedia ? matchMedia("(max-width: 600px)") : { matches: false };
    var bar = document.querySelector(".bar"), lastY = window.scrollY, touched = false;
    if (!bar) return;
    ["touchstart", "wheel", "keydown", "mousedown"].forEach(function (t) {
      window.addEventListener(t, function () { touched = true; }, { passive: true, once: true });
    });
    function show() { root.classList.remove("bar-away"); }
    function busy() {
      return (toc && toc.classList.contains("open")) || (panel && !panel.hidden) || (clipsPanel && !clipsPanel.hidden) || bar.contains(document.activeElement);
    }
    window.addEventListener("scroll", function () {
      var y = window.scrollY;
      if (!phoneNow.matches || !touched || y < 60 || busy()) { show(); lastY = y; return; }
      if (y > lastY + 8) { root.classList.add("bar-away"); lastY = y; }
      else if (y < lastY - 8) { show(); lastY = y; }
    }, { passive: true });
    bar.addEventListener("focusin", show);
  })();

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
