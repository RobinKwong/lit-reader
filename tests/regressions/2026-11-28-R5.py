"""R5: a PDF Title field that is the masthead (a running line) loses to the heading."""
import sys, io
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core
def done(tag, ok, got=""):
    print(tag, "pass" if ok else "FAIL %r" % (got,)); sys.exit(0 if ok else 1)

import tempfile
d = Path(tempfile.mkdtemp()); t = d / "p.txt"
mast = "Historical Studies in Education / Revue d’histoire de l’éducation"
t.write_text("\f".join(["x"] + ["%d %s\n\nbody\n" % (n, mast) for n in range(4)]), encoding="utf-8")
core.pdf_info = lambda pdf: {"Title": mast}
core.first_page_lines = lambda pdf: [(mast, 12.0), ("Read, Listen, Discuss, Act: Adult Education", 16.8), ("R.W. Sandwell", 10.7), ("OISE/University of Toronto", 8.4)]
found, how = core.guess_meta(d / "p.pdf", t)
done("R5", found["title"] == "Read, Listen, Discuss, Act: Adult Education" and found["authors"] == ["R.W. Sandwell"], found)
