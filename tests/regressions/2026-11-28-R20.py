"""R20: a title set smaller than a repeated masthead is still the title, even when it reads
like names or contains an affiliation word."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core

run = {core.line_key("Journal of Political Economy")}
bad = []
for title in ("Universities and Economic Growth in Europe", "Bank Capital Regulation and Financial Stability", "Hong Kong Economic Policy Studies"):
    got = core.guess_heading([("Journal of Political Economy", 24), (title, 18), ("Jane Smith", 12), ("Harvard University", 10), ("Abstract", 10)], run)
    if got[0] != title or got[1] != ["Jane Smith"]:
        bad.append(got)
print("R20", "pass" if not bad else "FAIL %r" % bad)
sys.exit(0 if not bad else 1)
