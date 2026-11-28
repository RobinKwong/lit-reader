"""R10: a title starting Introduction is not taken for the body heading."""
import sys, io
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core
def done(tag, ok, got=""):
    print(tag, "pass" if ok else "FAIL %r" % (got,)); sys.exit(0 if ok else 1)

got = core.guess_heading([("Introduction to the Special Issue on Rural Schooling", 16.8), ("Ana Ruiz", 10), ("University of Leeds", 8)], set())
done("R10", got[0] == "Introduction to the Special Issue on Rural Schooling", got)
