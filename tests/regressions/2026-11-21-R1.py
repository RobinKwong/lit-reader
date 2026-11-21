"""R1: a bundle line that is a PDF URL must stay a URL, not become a local path."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader.core import read_bundle

f = Path(tempfile.mkdtemp()) / "reading.txt"
f.write_text("https://arxiv.org/pdf/2508.08242.pdf\nhttp://example.org/paper.PDF\npapers/local.pdf\n", encoding="utf-8")
got = [it["input"] for it in read_bundle(f)["items"]]
ok = got[0] == "https://arxiv.org/pdf/2508.08242.pdf" and got[1] == "http://example.org/paper.PDF" \
     and got[2] == str(f.parent / "papers/local.pdf")
print("R1", "pass" if ok else "FAIL %r" % got)
sys.exit(0 if ok else 1)
