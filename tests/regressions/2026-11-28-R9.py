"""R9: author lines with a curly apostrophe or short all-caps surnames are read as names."""
import sys, io
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core
def done(tag, ok, got=""):
    print(tag, "pass" if ok else "FAIL %r" % (got,)); sys.exit(0 if ok else 1)

got = [core.name_list("Seán O’Brien and Jo Lee"), core.name_list("JING LI and WEI WU")]
done("R9", got[0] == ["Seán O’Brien", "Jo Lee"] and got[1] is not None, got)
