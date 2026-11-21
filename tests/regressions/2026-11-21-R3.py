"""R3: a local PDF that fails for want of a tool must not be told to download the PDF."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader.core import bundle_failure, ReaderError

e = ReaderError("couldn't get the full text:\n  pdf: The PDF route needs pdftoppm (brew install poppler)\n"
                "Try again later, or download the PDF and run: lit-reader paper.pdf")
reason, fix = bundle_failure(e, {"line": 5, "kind": "pdf"}, Path("reading.txt"))
ok = "download the pdf" not in (reason + fix).lower() and "pdftoppm" in reason + fix
print("R3", "pass" if ok else "FAIL %r / %r" % (reason, fix))
sys.exit(0 if ok else 1)
