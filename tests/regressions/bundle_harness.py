"""Runs `lit-reader bundle` offline: identify, take_route and finish_page are
replaced, so a test can say which papers fail and see what each page was given."""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from lit_reader import core  # noqa: E402


class Doc:
    def __init__(self, meta):
        self.meta, self.refs, self.nnotes = meta, [], 0


def run(lines, fail_route=(), fail_pages=()):
    """lines: the bundle file's lines. fail_route: inputs whose conversion fails.
    Returns (rendered, out, tmp): rendered holds a copy of each page's meta as it was rendered."""
    tmp = Path(tempfile.mkdtemp())
    pdf = tmp / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    (tmp / "reading.txt").write_text("# Test bundle\n" + "\n".join(lines) + "\n", encoding="utf-8")

    def identify(kind, value, given=None, advise=True):
        meta = {"pid": "pid-" + Path(value).stem, "title": "Paper about " + Path(value).stem,
                "authors": ["A Author"], "year": "2024", "venue": "", "pdf_path": str(pdf)}
        d = tmp / "work" / meta["pid"]
        d.mkdir(parents=True, exist_ok=True)
        return meta, d, pdf if kind == "pdf" else None

    def take_route(want, meta, d, pdf_, pages_):
        if pages_ in fail_pages:
            raise core.ReaderError("couldn't get the full text:\n  pdf: Docling failed:\nsome log\nTry again later")
        for f in fail_route:
            if f in meta["title"]:
                raise core.ReaderError("no open full text found. Download the PDF and run: lit-reader paper.pdf")
        return "arxiv", Doc(dict(meta))  # as the real routes do: the page's meta is a copy

    def finish_page(doc, meta, pages_=None):
        return "<html>%s</html>" % meta["pid"], 100, None

    def parse_input(s):
        return ("pdf", s) if s.endswith(".pdf") else ("doi", s)

    core.identify, core.take_route, core.finish_page = identify, take_route, finish_page
    core.report_coverage = lambda cov, doc: None
    core.parse_input = parse_input
    rendered = []
    orig_finish = core.finish_page

    def finish_and_record(doc, meta, pages_=None):
        rendered.append(dict(doc.meta))
        return orig_finish(doc, meta, pages_)

    core.finish_page = finish_and_record
    out = tmp / "out"
    a = argparse.Namespace(file=str(tmp / "reading.txt"), output=str(out), route="auto", epub=None, single_file=False)
    core.cmd_bundle(a)
    return rendered, out, tmp
