"""R16: a local PDF whose failure message names no pdf route still gets a real reason, not a dangling header."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader.core import bundle_failure, ReaderError

e = ReaderError("couldn't get the full text:\n  jats: Europe PMC timed out\nTry again later, or download the PDF and run: lit-reader paper.pdf")
reason, fix = bundle_failure(e, {"line": 3, "kind": "pdf"}, Path("b.txt"))
ok = "timed out" in reason and not reason.endswith(":")
print("R16", "pass" if ok else "FAIL %r / %r" % (reason, fix))
sys.exit(0 if ok else 1)
