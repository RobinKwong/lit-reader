"""R12: every index row of a bundle has its own data-pid, even a page range that failed."""
import re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bundle_harness import run

_, out, _ = run(["book.pdf pages=1-40", "book.pdf pages=41-80", "book.pdf"], fail_pages=("41-80",))
pids = re.findall(r'<li[^>]*data-pid="([^"]*)"', (out / "index.html").read_text(encoding="utf-8"))
ok = len(pids) == 3 and len(set(pids)) == 3
print("R12", "pass" if ok else "FAIL %r" % pids)
sys.exit(0 if ok else 1)
