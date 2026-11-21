"""R11: a local PDF that Docling fails on gets a readable reason and advice that fits."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader.core import bundle_failure, ReaderError

e = ReaderError("couldn't get the full text:\n  pdf: Docling failed:\n<log line>\n<log line>\n"
                "Try again later, or download the PDF and run: lit-reader paper.pdf")
reason, fix = bundle_failure(e, {"line": 5, "kind": "pdf"}, Path("reading.txt"))
tool = ReaderError("couldn't get the full text:\n  jats: timed out\n  pdf: The PDF route needs poppler's pdftoppm (macOS: brew install poppler)\nTry again")
r2, f2 = bundle_failure(tool, {"line": 5, "kind": "pdf"}, Path("reading.txt"))
ok = (reason == "Docling failed" and "line 5 of reading.txt" in fix and "download" not in fix.lower()
      and "pdftoppm" in r2 and "download" not in f2.lower())
print("R11", "pass" if ok else "FAIL %r / %r | %r / %r" % (reason, fix, r2, f2))
sys.exit(0 if ok else 1)
