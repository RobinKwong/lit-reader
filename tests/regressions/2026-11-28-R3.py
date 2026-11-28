"""R3: a title that is also the running head on later pages. Decided 28 November
2026: a repeated line is never taken as the title, and the output names the skipped line
and points to --title, so the wrong guess is visible."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core

lines = [("Attention Is All You Need", 16.8), ("Ana Ruiz and Jo Lee", 10.7), ("Google Brain", 8.4), ("Abstract", 9)]
d = Path(tempfile.mkdtemp()); t = d / "p.txt"
t.write_text("\f".join(["x"] + ["%d Attention Is All You Need\n\nbody\n" % n for n in range(4)]), encoding="utf-8")
core.pdf_info = lambda pdf: {}
core.first_page_lines = lambda pdf: lines
found, how = core.guess_meta(d / "p.pdf", t)
ok = found["title"] != "Attention Is All You Need" and "“Attention Is All You Need”" in how["title"] and "--title" in how["title"]
print("R3", "pass" if ok else "FAIL %r %r" % (found, how))
sys.exit(0 if ok else 1)
