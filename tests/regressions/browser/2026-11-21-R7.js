// R7: on a phone, "Aa" in the contents drawer must move keyboard focus into the settings panel.
// Run with chrome-devtools evaluate_script on any paper page of a built bundle, viewport 390 wide.
// Returns "pass" or "FAIL ...".
async () => {
  const toggle = document.getElementById("toc-toggle");
  toggle.click();
  await new Promise(r => setTimeout(r, 100));
  const proxy = document.querySelector('nav.toc [data-proxy="aa"]');
  if (!proxy) return "FAIL no Aa in the drawer (is the viewport 600 px or less?)";
  proxy.focus();
  proxy.click();
  await new Promise(r => setTimeout(r, 100));
  const panel = document.getElementById("panel");
  const ok = !panel.hidden && panel.contains(document.activeElement);
  const where = document.activeElement && (document.activeElement.id || document.activeElement.textContent.trim().slice(0, 30));
  const msg = ok ? "pass" : "FAIL panel hidden=" + panel.hidden + ", focus on " + where;
  if (!panel.hidden) document.getElementById("aa").click();  // leave the page as found
  return msg;
}
