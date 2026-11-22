// P4: undoing "Mark as finished" must put back the status the paper had before,
// including "In progress" saved by an earlier version (state "started", no read paragraphs).
// Run with chrome-devtools evaluate_script on any paper page. It restores the paper's status afterwards.
// Returns "pass" or "FAIL ...".
() => {
  const key = "litreader.status." + document.body.dataset.pid;
  const btn = document.getElementById("mark-done");
  if (!btn) return "FAIL no Mark as finished button";
  const saved = localStorage.getItem(key);
  const cases = [{ state: "started", pos: "b3" }, { pos: "b3" }, { state: "started", pos: "b3", read: ["b3"], pct: 0.1 }];
  const out = [];
  cases.forEach(c => {
    localStorage.setItem(key, JSON.stringify(c));
    btn.click(); btn.click();
    const st = JSON.parse(localStorage.getItem(key));
    if ((st.state || "") !== (c.state || "")) out.push(JSON.stringify(c) + " came back as state " + (st.state || "none"));
  });
  if (saved === null) localStorage.removeItem(key); else localStorage.setItem(key, saved);
  document.querySelectorAll(".toast").forEach(t => t.remove());
  return out.length ? "FAIL " + out.join("; ") : "pass";
}
