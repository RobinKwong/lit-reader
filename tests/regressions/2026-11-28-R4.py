"""R4: without a system word list, a title-case title is not mistaken for names."""
import sys, io
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core
def done(tag, ok, got=""):
    print(tag, "pass" if ok else "FAIL %r" % (got,)); sys.exit(0 if ok else 1)

core.COMMON = set()
got = core.guess_heading([("Teaching History, Public Memory and Civic Identity", 16.8), ("Ana Ruiz", 10.7), ("University of Leeds", 8.4)], set())
done("R4", got[0] == "Teaching History, Public Memory and Civic Identity" and got[1] == ["Ana Ruiz"], got)
