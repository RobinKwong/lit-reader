// P1: a paragraph behind the full-screen figure viewer must not be counted as read,
// and the same paragraph must be counted once the viewer is closed (the control).
// Run with chrome-devtools evaluate_script on a paper page with figures (Tessler, Setala),
// viewport under 1261 px wide, so a figure opens in the viewer. Takes about 20 s.
// Returns "pass" or "FAIL ...".
async () => {
  const key = "litreader.status." + document.body.dataset.pid;
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const poke = () => window.dispatchEvent(new PointerEvent("pointermove"));
  const readNow = () => new Set((JSON.parse(localStorage.getItem(key) || "{}").read) || []);
  const fig = document.querySelector(".fig-zoom");
  if (!fig) return "FAIL no figure on this page";
  const before = readNow();
  const p = [...document.querySelectorAll('main [data-body="1"]')].find(b => +b.dataset.w >= 5 && +b.dataset.w <= 40 && !before.has(b.id));
  if (!p) return "FAIL no short unread paragraph";
  const place = () => { p.scrollIntoView(); window.scrollBy(0, -90); };  // first in view, under the bar
  place(); await wait(300);
  fig.click(); await wait(300);
  if (!document.querySelector(".viewer")) return "FAIL the viewer did not open (is the viewport 1261 px or wider?)";
  for (let i = 0; i < 9; i++) { poke(); await wait(1000); }
  const during = readNow();
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); await wait(300);
  if (during.has(p.id)) return "FAIL " + p.id + " was counted as read behind the viewer";
  place();
  for (let i = 0; i < 9; i++) { poke(); await wait(1000); }
  return readNow().has(p.id) ? "pass" : "FAIL control: " + p.id + " was not counted with the viewer closed";
}
