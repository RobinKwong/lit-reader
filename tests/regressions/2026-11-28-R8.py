"""R8: dated publication lines (with a day number, or mid-line after ;) give the year."""
import sys, io
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core
def done(tag, ok, got=""):
    print(tag, "pass" if ok else "FAIL %r" % (got,)); sys.exit(0 if ok else 1)

got = [core.guess_year(x, {})[0] for x in ["Received 12 March 2011; accepted 3 June 2012", "Received: March 12, 2011", "Published online: 14 May 2012"]]
done("R8", got == [2012, 2011, 2012], got)
