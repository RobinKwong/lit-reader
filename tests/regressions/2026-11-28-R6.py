"""R6: a Title field that is the start of the heading keeps the authors found under it."""
import sys, io
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core
def done(tag, ok, got=""):
    print(tag, "pass" if ok else "FAIL %r" % (got,)); sys.exit(0 if ok else 1)

import tempfile
d = Path(tempfile.mkdtemp()); t = d / "p.txt"; t.write_text("x", encoding="utf-8")
core.pdf_info = lambda pdf: {"Title": "Read, Listen, Discuss, Act"}
core.first_page_lines = lambda pdf: [("‘Read, Listen, Discuss, Act’: Adult Education and the Forum", 16.8), ("R.W. Sandwell", 10.7), ("OISE/University of Toronto", 8.4)]
found, how = core.guess_meta(d / "p.pdf", t)
done("R6", found["authors"] == ["R.W. Sandwell"], found)
