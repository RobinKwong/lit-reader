"""R6: two page ranges of one PDF must get different ids, or they share status, quotes and position."""
import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from bundle_harness import run

rendered, _, tmp = run(["book.pdf pages=1-40", "book.pdf pages=41-80"])
pids = [m["pid"] for m in rendered]
member_pids = sorted({m["pid"] for m in rendered[0]["bundle_members"]})
ok = len(pids) == 2 and len(set(pids)) == 2 and member_pids == sorted(pids)
print("R6", "pass" if ok else "FAIL pids %r members %r" % (pids, member_pids))
sys.exit(0 if ok else 1)
