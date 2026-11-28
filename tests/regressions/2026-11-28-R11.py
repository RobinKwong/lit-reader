"""R11: a masthead in the largest type that repeats on later pages is not the title."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core
def done(tag, ok, got=""):
    print(tag, "pass" if ok else "FAIL %r" % (got,)); sys.exit(0 if ok else 1)

run = {core.line_key("Journal of Political Economy")}
got = core.guess_heading([("Journal of Political Economy", 20), ("Trade Costs and Growth in Small Economies", 16), ("Jane Smith and John Doe", 11), ("University of Chicago", 9), ("Abstract", 10)], run)
done("R11", got[0] == "Trade Costs and Growth in Small Economies" and got[1] == ["Jane Smith", "John Doe"], got)
