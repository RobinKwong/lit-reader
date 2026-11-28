"""R12: all-caps author lines split at AND and come out in one consistent case."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core
def done(tag, ok, got=""):
    print(tag, "pass" if ok else "FAIL %r" % (got,)); sys.exit(0 if ok else 1)

got = [core.name_list("JOHN KIM AND LEE WU"), core.name_list("MARY ANN LEE, LI XU")]
done("R12", got == [["John Kim", "Lee Wu"], ["Mary Ann Lee", "Li Xu"]], got)
