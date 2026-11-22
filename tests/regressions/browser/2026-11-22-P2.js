// P2: a paper opened and left alone, with no scrolling, typing or pointer, must not count anything as read.
// Run with chrome-devtools evaluate_script on any paper page, twice, touching nothing in between:
// the first run clears this paper's reading status and reloads the page at a heading just above a
// short paragraph; the second run, at least 12 s later, checks that nothing was counted.
// Returns "set up: run again in 12 s", "pass" or "FAIL ...".
async () => {
  const key = "litreader.status." + document.body.dataset.pid, flag = "litreader.test.P2";
  const was = sessionStorage.getItem(flag);
  if (was) {
    sessionStorage.removeItem(flag);
    if (Date.now() - +was < 12000) return "FAIL ran too soon: wait 12 s after the first run";
    const st = JSON.parse(localStorage.getItem(key) || "{}");
    return (st.read || []).length ? "FAIL counted as read with no input: " + st.read.join(", ") : "pass";
  }
  const head = [...document.querySelectorAll("main [data-sec][id]")].find(h => {
    const n = h.nextElementSibling;
    return n && n.getAttribute("data-body") === "1" && +n.dataset.w >= 5 && +n.dataset.w <= 60;
  });
  if (!head) return "FAIL no heading followed by a short paragraph";
  localStorage.removeItem(key);
  sessionStorage.setItem(flag, String(Date.now()));
  location.replace(location.pathname + "#" + head.id);
  location.reload();
  return "set up: run again in 12 s";
}
