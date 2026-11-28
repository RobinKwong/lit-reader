"""G1: a PDF with no record must not take its masthead for the title, or one end
of a date range in the title for the year. Pattern from Sandwell 2012, Historical
Studies in Education: masthead, then a three-line title, then the author line.
Also: --title, --author and --year replace the guesses."""
import io, sys, tempfile
from contextlib import redirect_stdout
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core

FIRST = """170

Historical Studies in Education / Revue d’histoire de l’éducation
SPECIAL ISSUE / NUMÉRO spécial

‘Read, Listen, Discuss, Act’:
Adult Education, Rural Citizenship and the
Canadian National Farm Radio Forum 1941–1965
R.W. Sandwell
OISE/University of Toronto

Abstract

The Canadian National Farm Radio Forum was launched in January 1941. During the winter
months from 1941 to 1965, the Farm Radio Forum supplemented weekly radio broadcasts.
"""
LATER = ["Special Issue/Numéro spécial %d\n\nbody text on an odd page\nmore body\n" if n % 2 else
         "%d Historical Studies in Education/Revue d’histoire de l’éducation\n\nbody text on an even page\nmore\n"
         for n in range(171, 177)]
LATER = [x % n for x, n in zip(LATER, range(171, 177))]
TITLE = ("‘Read, Listen, Discuss, Act’: Adult Education, Rural Citizenship and the "
         "Canadian National Farm Radio Forum 1941–1965")

d = Path(tempfile.mkdtemp())
text = d / "paper.txt"
text.write_text("\f".join([FIRST] + LATER), encoding="utf-8")
fails = []


# Line heights as poppler reports them for the real PDF, except that the masthead
# is set as large as the title here, so only its repeating on later pages rules it out.
HEIGHTS = {"170": 10.9, "Historical": 16.8, "SPECIAL": 10.8, "\u2018Read": 16.8, "Adult": 16.8, "Canadian": 16.8,
           "R.W.": 10.7, "OISE": 8.4, "Abstract": 9.7}
BOXES = [(x.strip(), next((h for k, h in HEIGHTS.items() if x.startswith(k)), 10.1)) for x in FIRST.splitlines() if x.strip()]


def build(info, boxes=BOXES):
    core.pdf_info = lambda pdf: info
    core.first_page_lines = lambda pdf: boxes
    out = io.StringIO()
    with redirect_stdout(out):
        meta = core.settle_meta(core.pdf_meta(d / "paper.pdf", text, "k"))
    return meta, out.getvalue()


meta, said = build({"Creator": "Adobe InDesign CS5 (7.0)", "CreationDate": "Tue Apr 24 14:13:31 2012 BST"})
if meta["title"] != TITLE:
    fails.append("title %r" % meta["title"])
if meta["authors"] != ["R.W. Sandwell"]:
    fails.append("authors %r" % meta["authors"])
if meta["year"] != 2012:
    fails.append("year %r" % meta["year"])
if core.slug(meta) != "sandwell-2012-read-listen-discuss-act":
    fails.append("slug %r" % core.slug(meta))
for bit in ("guessed", "Historical Studies in Education / Revue", "R.W. Sandwell", "2012 (the PDF's creation date)", "--title"):
    if bit not in said:
        fails.append("output lacks %r" % bit)

# no usable PDF date (a scan): the year stays blank rather than 1941 or 1965
meta, said = build({"Producer": "ABBYY FineReader", "CreationDate": "2019"})
if meta["year"] is not None:
    fails.append("scan year %r" % meta["year"])
if "year:    left blank" not in said:
    fails.append("blank year not reported: %r" % said)

# without layout boxes (plain text only): the same title, but no authors guessed
meta, said = build({}, [])
if meta["title"] != TITLE or meta["authors"] != [] or meta["year"] is not None:
    fails.append("plain text %r" % ((meta["title"], meta["authors"], meta["year"]),))

# overrides win over the guesses and are reported as given
a = core.standalone_parser().parse_args(["x.pdf", "--title", "Right title", "--author", "R.W. Sandwell",
                                         "--author", "A. N. Other", "--year", "2012"])
core.pdf_info = lambda pdf: {}
core.first_page_lines = lambda pdf: BOXES
out = io.StringIO()
with redirect_stdout(out):
    meta = core.settle_meta(core.pdf_meta(d / "paper.pdf", text, "k"), core.given_meta(a))
if (meta["title"], meta["authors"], meta["year"]) != ("Right title", ["R.W. Sandwell", "A. N. Other"], 2012):
    fails.append("overrides %r" % ((meta["title"], meta["authors"], meta["year"]),))
if "guessed" in out.getvalue() or "as given with --year" not in out.getvalue():
    fails.append("override output %r" % out.getvalue())
a = core.standalone_parser().parse_args(["x.pdf", "--author", "", "--year", ""])
g = core.given_meta(a)
if g != {"title": None, "authors": [], "year": "", "venue": None}:
    fails.append("blanking overrides %r" % g)

print("G1", "pass" if not fails else "FAIL " + "; ".join(fails))
sys.exit(0 if not fails else 1)
