"""R7: a bundle must not advise --title, which bundles do not take."""
import sys, io
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core
def done(tag, ok, got=""):
    print(tag, "pass" if ok else "FAIL %r" % (got,)); sys.exit(0 if ok else 1)

meta = {"title": "T", "authors": [], "year": None, "guessed": {"title": "the first page", "authors": "none", "year": "none"}}
out = io.StringIO()
with redirect_stdout(out):
    core.settle_meta(meta, None, advise=False)
done("R7", "--title" not in out.getvalue() and "guessed" in out.getvalue(), out.getvalue())
