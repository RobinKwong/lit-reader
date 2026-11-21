"""R2: a paper whose conversion fails must not be linked from the other papers."""
import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from bundle_harness import run

rendered, out, _ = run(["10.1/alpha", "10.1/beta", "10.1/gamma"], fail_route=("gamma",))
links = {m["href"] for meta in rendered for m in meta.get("bundle_members") or []}
ok = links and not any("gamma" in h for h in links) and not (out / "paper-about-gamma.html").exists()
print("R2", "pass" if ok else "FAIL members %r" % sorted(links))
sys.exit(0 if ok else 1)
