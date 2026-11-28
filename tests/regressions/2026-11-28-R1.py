"""R1: --title must win over the title_html an arXiv or Europe PMC source sets."""
import sys, io
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core

meta = {"title": "Old", "authors": [], "year": 2020, "title_html": "Old <i>x</i>"}
with redirect_stdout(io.StringIO()):
    core.settle_meta(meta, {"title": "My title"})
core.set_title_html(meta, "Source <i>title</i>")  # what arxiv_doc and jats_doc do with the source's title
plain = {"title": "Found"}
core.set_title_html(plain, "Found <i>it</i>")      # without --title the source's markup is kept
ok = "title_html" not in meta and plain.get("title_html") == "Found <i>it</i>"
print("R1", "pass" if ok else "FAIL %r %r" % (meta, plain))
sys.exit(0 if ok else 1)
