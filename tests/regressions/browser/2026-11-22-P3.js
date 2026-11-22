// P3: on the index, a two-line status with its bar must not push a paper's description away from its title.
// Run with chrome-devtools evaluate_script on a built index page, viewport 1440 wide.
// It gives the first row a one-line title and a long status (no storage touched; reload to undo).
// Returns "pass" or "FAIL ...".
() => {
  const rows = [...document.querySelectorAll(".list li[data-pid]")].filter(li => li.querySelector(".t") && li.querySelector(".d"));
  if (!rows.length) return "FAIL no rows";
  const li = rows[0];
  li.querySelector(".t a").textContent = "Attention Is All You Need";  // a short title, as many papers have
  const s = li.querySelector(".s");
  s.textContent = ""; s.className = "s started";
  ["About 45% read", "last read 3 weeks ago (1 Nov)", "2 quotes"].forEach((t, k) => {
    if (k) s.appendChild(document.createTextNode(" · "));
    const part = document.createElement("span"); part.className = "part"; part.textContent = t; s.appendChild(part);
  });
  const m = document.createElement("span"); m.className = "meter"; const f = document.createElement("span"); f.style.width = "45%"; m.appendChild(f); s.appendChild(m);
  const gap = li.querySelector(".d").getBoundingClientRect().top - li.querySelector(".t a").getBoundingClientRect().bottom;  // the title text: its grid cell stretches to the row
  return gap <= 10 ? "pass" : "FAIL description sits " + Math.round(gap) + " px below its title";
}
