"""R2: a title containing school, college, centre or institution is still a title."""
import sys, io
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core
def done(tag, ok, got=""):
    print(tag, "pass" if ok else "FAIL %r" % (got,)); sys.exit(0 if ok else 1)

got = core.guess_heading([("Institutional Change in Rural Schools, 1880-1920", 16.8), ("Jo Lee", 10.7), ("OISE/University of Toronto", 8.4)], set())
done("R2", got[0] == "Institutional Change in Rural Schools, 1880-1920" and got[1] == ["Jo Lee"], got)
