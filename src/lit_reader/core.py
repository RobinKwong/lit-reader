#!/usr/bin/env python3
"""lit_reader.py: reading versions of academic papers as local HTML pages.

Each paper becomes one HTML page, styled for long reading: about 65 characters
a line, a choice of fonts, light, sepia or dark, a contents sidebar with time
left, citations that open as cards, notes and page numbers in the margins,
and a saved reading position.

The lit.py cache (~/.cache/lit) is never written to: the ledger's claims and
reads store character offsets into it. Sources fetched for reading live in
~/.cache/lit-reader/src/<slug>/.

Routes, best first:
  arxiv   arXiv's own HTML (LaTeXML): real headings, linked citations.
  jats    Europe PMC full-text XML (JATS): the same, for PMC papers.
  pdf     Docling's JSON from the cached PDF, with figures and tables cropped
          from the PDF page by pdftoppm. Run Docling first (see `pdf-convert`).

Standalone use needs no ledger:
  lit-reader PDF | ARXIV-ID-OR-URL | DOI | PMCID [-o DIR] [--route R] [--pages A-B]
Metadata comes from arXiv, Crossref or Europe PMC, or failing those the PDF's
first page. The page is written to ./<slug>/index.html. A local PDF is always
the source unless --route online asks for arXiv's or Europe PMC's version.

Ledger commands read their paths from a settings file, by default
~/.config/lit-reader/config.toml (LIT_READER_CONFIG points elsewhere):
  output_dir = "~/papers/reader"         required
  list_file = "~/papers/list.json"       default: list.json in output_dir
  must_read_file = "~/papers/reading.md" optional
  lit_cache = "~/.cache/lit"             optional
  index_bar, index_kicker, index_note    optional wording for the index page
  [ledgers]
  main = "~/papers/ledger.sqlite"        names usable as --ledger or in the list

  fetch  --route arxiv|jats --pid PID --ledger DB   download the structured source (online)
  pdf-convert --pid PID --ledger DB [--pages A-B]   run Docling on the cached PDF (offline)
  build  --pid PID --ledger DB --route R [--list-n N] [--pages A-B]   write the page (offline)
  index                                              write index.html from list.json
  all                                                build every list.json entry that has a route

Every build prints a coverage check: the share of the cached pdftotext words
that reached the page, and the longest runs that did not. Those are the places
to look for dropped text.

SECURITY: fetched HTML, XML and PDFs are untrusted. Pages are built only from
whitelisted tags with escaped text; images are embedded only after checking
their magic bytes; PDFs are read only by Docling and pdftoppm, given paths as
arguments, never through a shell.
"""
import argparse
import base64
import datetime
import hashlib
import html
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from . import __version__

HERE = Path(__file__).resolve().parent
HOME = Path.home()
LIT_CACHE = Path(os.environ.get("LIT_CACHE", "~/.cache/lit")).expanduser()
CONFIG = Path(os.environ.get("LIT_READER_CONFIG") or
              Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config") / "lit-reader" / "config.toml").expanduser()
WORK = HOME / ".cache" / "lit-reader"
SRC = WORK / "src"
FONTS = HERE / "fonts"
OUT = None              # the settings below fill these in for the ledger commands
LIST_FILE = None
PROJECT_READING = None
LEDGERS = {}
INDEX_TEXT = {"index_bar": "Reading copies", "index_kicker": "Papers", "index_note": ""}
WPM = 200  # must match reader.js
UA = "lit-reader/%s (offline reading tool)" % __version__


class ReaderError(Exception):
    pass


def read_settings(path):
    """The small part of TOML the settings file uses: comments, [sections] and
    key = "string" lines. (tomllib needs Python 3.11; this tool supports 3.9.)"""
    out = {}
    section = out
    for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"\[([A-Za-z0-9_-]+)\]", line)
        if m:
            section = out.setdefault(m.group(1), {})
            continue
        m = re.fullmatch(r"""([A-Za-z0-9_-]+)\s*=\s*(?:"([^"\\]*)"|'([^']*)')\s*(?:#.*)?""", line)
        if not m:
            raise ReaderError("%s line %d: expected key = \"value\"" % (path, no))
        section[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    return out


def apply_settings():
    """Load the paths the ledger commands need. Standalone builds never call this."""
    global OUT, LIST_FILE, PROJECT_READING, LIT_CACHE
    conf = read_settings(CONFIG) if CONFIG.is_file() else {}
    out = os.environ.get("LIT_READER_OUT") or conf.get("output_dir")
    if not out:
        raise ReaderError("ledger commands need a settings file with output_dir: %s" % CONFIG)
    OUT = Path(out).expanduser()
    LIST_FILE = Path(conf["list_file"]).expanduser() if conf.get("list_file") else OUT / "list.json"
    PROJECT_READING = Path(conf["must_read_file"]).expanduser() if conf.get("must_read_file") else None
    if conf.get("lit_cache") and not os.environ.get("LIT_CACHE"):
        LIT_CACHE = Path(conf["lit_cache"]).expanduser()
    LEDGERS.update(conf.get("ledgers") or {})
    INDEX_TEXT.update({k: conf[k] for k in INDEX_TEXT if k in conf})


def esc(s):
    return html.escape(s, quote=False)


def attr(s):
    return html.escape(s, quote=True)


def safe_id(s):
    return re.sub(r"[^A-Za-z0-9_-]", "-", s)


def words(text):
    return len(re.findall(r"\w+", text))


def strip_tags(h):
    return html.unescape(re.sub(r"<[^>]+>", " ", h))


# --------------------------------------------------------------------------
# A small DOM, shared by every route
# --------------------------------------------------------------------------

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr", "mspace", "none", "mprescripts"}


class Node(object):
    __slots__ = ("tag", "attrs", "kids", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.kids = []
        self.parent = parent

    def cls(self):
        return set((self.attrs.get("class") or "").split())

    def text(self):
        return "".join(k if isinstance(k, str) else k.text() for k in self.kids)

    def iter(self):
        yield self
        for k in self.kids:
            if isinstance(k, Node):
                for d in k.iter():
                    yield d

    def find(self, pred):
        for d in self.iter():
            if d is not self and pred(d):
                return d
        return None

    def findall(self, pred):
        return [d for d in self.iter() if d is not self and pred(d)]

    def children(self):
        return [k for k in self.kids if isinstance(k, Node)]


class DomBuilder(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.root = Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, [(k, v or "") for k, v in attrs], self.cur)
        self.cur.kids.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.kids.append(Node(tag, [(k, v or "") for k, v in attrs], self.cur))

    def handle_endtag(self, tag):
        c = self.cur
        while c is not self.root and c.tag != tag:
            c = c.parent
        if c is not self.root:
            self.cur = c.parent

    def handle_data(self, data):
        self.cur.kids.append(data)


def parse_html(text):
    b = DomBuilder()
    b.feed(text)
    b.close()
    return b.root


def local(name):
    return name.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def et_to_node(e, parent=None):
    n = Node(local(e.tag), {local(k): v for k, v in e.attrib.items()}, parent)
    if e.text:
        n.kids.append(e.text)
    for c in e:
        n.kids.append(et_to_node(c, n))
        if c.tail:
            n.kids.append(c.tail)
    return n


# --------------------------------------------------------------------------
# Safe output: only these tags and attributes ever reach a page
# --------------------------------------------------------------------------

DROP = {"script", "style", "annotation", "annotation-xml", "svg", "iframe", "object", "embed",
        "noscript", "template", "button", "form", "input", "textarea", "select", "link", "meta",
        "img", "video", "audio", "canvas", "tex-math", "inline-graphic", "head", "title"}
SIMPLE = {"em": "em", "i": "em", "italic": "em", "strong": "strong", "b": "strong", "bold": "strong",
          "sup": "sup", "sub": "sub", "code": "code", "monospace": "code", "sc": "span", "u": "u",
          "underline": "u", "small": "small"}
MATHML = {
    "math": ("display",), "mi": ("mathvariant",), "mo": ("stretchy", "fence", "separator", "form", "lspace", "rspace", "largeop", "movablelimits"),
    "mn": (), "mrow": (), "msub": (), "msup": (), "msubsup": (), "mfrac": ("linethickness",),
    "msqrt": (), "mroot": (), "mover": ("accent",), "munder": ("accentunder",), "munderover": (),
    "mtext": (), "mspace": ("width",), "mtable": (), "mtr": (), "mtd": ("columnspan",), "semantics": (),
    "mstyle": ("displaystyle", "scriptlevel"), "mpadded": (), "mphantom": (), "mmultiscripts": (),
    "mprescripts": (), "none": (), "menclose": ("notation",), "ms": (),
}
TABLE = {"table": (), "thead": (), "tbody": (), "tfoot": (), "tr": (), "th": ("colspan", "rowspan"),
         "td": ("colspan", "rowspan"), "caption": ()}
ATTR_OK = re.compile(r"^[\w .%#:-]{0,40}$")


def math_html(n):
    """MathML, whitelisted; annotations (LaTeX source) dropped."""
    if isinstance(n, str):
        return esc(n)
    if n.tag in DROP:
        return ""
    inner = "".join(math_html(k) for k in n.kids)
    if n.tag not in MATHML:
        return inner
    attrs = "".join(' %s="%s"' % (a, attr(n.attrs[a])) for a in MATHML[n.tag]
                    if a in n.attrs and ATTR_OK.match(n.attrs[a]))
    if n.tag == "math":
        return '<math%s>%s</math>' % (attrs, inner)
    return "<%s%s>%s</%s>" % (n.tag, attrs, inner, n.tag)


def safe_href(h):
    h = (h or "").strip()
    if h.startswith("#"):
        return "#" + safe_id(h[1:])
    p = urllib.parse.urlparse(h)
    if p.scheme in ("http", "https") and p.netloc:
        return h
    return None


class Inline(object):
    """Turns a node's children into safe inline HTML. A route subclasses
    `rule` to handle its own citation, note and link markup."""

    def __init__(self, doc):
        self.doc = doc

    def run(self, node):
        return "".join(self.one(k) for k in node.kids)

    def rule(self, n):
        return None

    def one(self, k):
        if isinstance(k, str):
            return esc(k)
        r = self.rule(k)
        if r is not None:
            return r
        t = k.tag
        if t in DROP:
            return ""
        if t in SIMPLE:
            inner = self.run(k)
            if not inner.strip():
                return inner
            tag = SIMPLE[t]
            if t == "sc":
                return '<span style="font-variant:small-caps">%s</span>' % inner
            return "<%s>%s</%s>" % (tag, inner, tag)
        if t == "br":
            return "<br>"
        if t == "math":
            return math_html(k)
        if t in ("a", "ext-link", "uri"):
            href = safe_href(k.attrs.get("href") or k.attrs.get("xlink:href") or k.attrs.get("href", ""))
            inner = self.run(k)
            if href and not href.startswith("#"):
                return '<a href="%s" rel="noopener noreferrer">%s</a>' % (attr(href), inner)
            if href:
                return '<a href="%s">%s</a>' % (attr(href), inner)
            return inner
        if t in TABLE:
            attrs = "".join(' %s="%s"' % (a, attr(k.attrs[a])) for a in TABLE[t]
                            if a in k.attrs and re.match(r"^\d{1,2}$", k.attrs[a]))
            cls = ' class="data"' if t == "table" else ""
            return "<%s%s%s>%s</%s>" % (t, cls, attrs, self.run(k), t)
        if t in ("ul", "ol", "li", "list", "list-item"):
            tag = {"list": "ul", "list-item": "li"}.get(t, t)
            return "<%s>%s</%s>" % (tag, self.run(k), tag)
        if t in ("p", "div") and k.parent is not None and k.parent.tag in ("td", "th", "li", "list-item"):
            return self.run(k) + " "
        return self.run(k)


# --------------------------------------------------------------------------
# The document model and the page renderer
# --------------------------------------------------------------------------

class Doc(object):
    def __init__(self, meta):
        self.meta = meta          # title, authors, year, venue, doi, pid, url
        self.abstracts = []       # (heading, html)
        self.blocks = []          # dicts, see render()
        self.refs = []            # (id, html)
        self.ref_ids = set()
        self.nnotes = 0
        self.source = ""          # one line: where the text came from
        self.pdf = None           # Path of the cached PDF, for page links

    def note(self, inner_html):
        self.nnotes += 1
        n = self.nnotes
        return ('<span class="sn-mark" data-for="sn-%d" role="button" tabindex="0" aria-label="note %d">%d</span>'
                '<span class="sidenote" id="sn-%d"><span class="n">%d</span>%s</span>') % (n, n, n, n, n, inner_html)

    def add(self, **b):
        self.blocks.append(b)

    def cite(self, ids, inner):
        ids = [safe_id(i) for i in ids if i]
        if not ids:
            return inner
        return '<a class="cite" href="#ref-%s" data-ref="%s">%s</a>' % (ids[0], attr(" ".join(ids)), inner)


AUTHORS_SHOWN = 3   # a list longer than AUTHORS_MAX opens with this many names
AUTHORS_MAX = 5


def authors_html(authors):
    """The byline. A long author list starts collapsed, so the paper comes first."""
    if len(authors) <= AUTHORS_MAX:
        return '<p class="authors">%s</p>' % esc(", ".join(authors))
    rest = len(authors) - AUTHORS_SHOWN
    return ('<p class="authors">%s<span class="au-rest" id="au-rest" hidden>, %s</span> '
            '<button class="au-toggle" id="au-toggle" type="button" aria-expanded="false" aria-controls="au-rest" data-more="Show %d more">'
            '<span class="au-label">Show %d more</span><span class="au-chevron" aria-hidden="true"></span></button></p>') % (
        esc(", ".join(authors[:AUTHORS_SHOWN])), esc(", ".join(authors[AUTHORS_SHOWN:])), rest, rest)


def image_size(src):
    """(width, height) of an embedded image, so the page doesn't shift as images load."""
    try:
        d = base64.b64decode(src.split(",", 1)[1])
    except (IndexError, ValueError):
        return None
    if d[:8] == b"\x89PNG\r\n\x1a\n" and len(d) >= 24:
        return int.from_bytes(d[16:20], "big"), int.from_bytes(d[20:24], "big")
    if d[:3] == b"GIF" and len(d) >= 10:
        return int.from_bytes(d[6:8], "little"), int.from_bytes(d[8:10], "little")
    i = 2
    while d[:2] == b"\xff\xd8" and i + 9 < len(d):
        if d[i] != 0xFF:
            return None
        m = d[i + 1]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(d[i + 7:i + 9], "big"), int.from_bytes(d[i + 5:i + 7], "big")
        i += 2 + int.from_bytes(d[i + 2:i + 4], "big")
    return None


def img_tag(src, alt):
    alt = "" if (alt or "").strip().lower() == "refer to caption" else (alt or "")  # arXiv's placeholder; the caption follows
    size = image_size(src)
    dims = ' width="%d" height="%d"' % size if size else ""
    return '<img src="%s" alt="%s"%s loading="lazy">' % (src, attr(alt), dims)


def pdf_href(doc):
    """Standalone pages link to their own copy of the PDF, so no local path is written into the page."""
    return doc.meta.get("pdf_href") or doc.pdf.as_uri()


def pdf_link(doc, page):
    if not doc.pdf or not page:
        return ""
    return '<a class="pdf-link" href="%s#page=%d">open page %d of the PDF</a>' % (attr(pdf_href(doc)), page, page)


def render(doc, list_line=None, list_pos=None):
    """Doc -> page HTML."""
    m = doc.meta
    out, toc = [], []
    used = set()
    sec_id = ""
    body = True
    bid = 0
    # words per heading, for the contents sidebar
    heads = [i for i, b in enumerate(doc.blocks) if b["t"] == "h"]
    sec_words = {}
    for n, i in enumerate(heads):
        lvl = doc.blocks[i]["level"]
        w = 0
        for b in doc.blocks[i + 1:]:
            if b["t"] == "h" and b["level"] <= lvl:
                break
            w += b.get("_w", 0) or words(strip_tags(block_text(b)))
        sec_words[i] = w

    for i, b in enumerate(doc.blocks):
        t = b["t"]
        bid += 1
        if t == "h":
            hid = b.get("id") or "s-" + safe_id(strip_tags(b["html"]).strip().lower())[:40]
            while hid in used:
                hid += "-"
            used.add(hid)
            sec_id = hid
            if b.get("appendix") and body:
                body = False
                out.append('<div class="appendix-start"></div>')
            lvl = min(max(b["level"], 2), 4)
            b["html"] = re.sub(r"\.\s*$", "", b["html"].strip())  # run-in heads: "Control Variables."
            title = strip_tags(b["html"]).strip()
            no = '<span class="secno">%s</span>' % esc(b["no"]) if b.get("no") else ""
            out.append('<h%d id="%s" data-sec="1" data-title="%s">%s%s</h%d>' % (
                lvl, hid, attr(((b.get("no") or "") + " " + title).strip()), no, b["html"], lvl))
            if lvl <= 3:
                mins = max(1, round(sec_words.get(i, 0) / float(WPM)))
                toc.append((lvl, hid, ((b.get("no") or "") + " " + title).strip(), mins))
            continue
        w = words(strip_tags(block_text(b)))
        common = 'id="b%d" data-w="%d" data-in="%s" data-body="%d"' % (bid, w, sec_id, 1 if body else 0)
        if t == "p":
            out.append("<p %s>%s</p>" % (common, chunked(b["html"])))
        elif t == "page":
            out.append('<span class="pg" id="pg-%s">%s</span>' % (
                safe_id(str(b["label"])), (pdf_anchor(doc, b) or "p. " + esc(str(b["label"])))))
        elif t == "list":
            tag = "ol" if b.get("ordered") else "ul"
            out.append("<%s %s>%s</%s>" % (tag, common, "".join("<li>%s</li>" % x for x in b["items"]), tag))
        elif t == "eq":
            out.append('<div class="eq" %s>%s</div>' % (common, b["html"]))
        elif t == "pre":
            out.append('<pre class="listing" %s>%s</pre>' % (common, esc(b["text"])))
        elif t == "fig":
            parts = []
            for src, alt in b.get("imgs") or []:
                parts.append(img_tag(src, alt))
            if b.get("table"):
                parts.append('<div class="tablewrap">%s</div>' % b["table"])
            if not parts:
                parts.append('<div class="missing-figure">This %s did not come through in the source. %s</div>' % (
                    "table" if b.get("kind") == "table" else "figure", pdf_link(doc, b.get("page")) or ""))
            cap = ""
            if b.get("label") or b.get("caption"):
                link = pdf_link(doc, b.get("page")) if (b.get("imgs") or b.get("table")) else ""
                cap = "<figcaption>%s%s%s</figcaption>" % (
                    '<span class="label">%s</span>' % esc(b["label"]) if b.get("label") else "",
                    b.get("caption") or "", (" " + link) if link else "")
            fid = ' data-fig="%s"' % attr(b["id"]) if b.get("id") else ""
            out.append('<figure %s%s>%s%s</figure>' % (common.replace('id="b%d"' % bid, 'id="%s"' % (b.get("id") or "b%d" % bid)), fid, "".join(parts), cap))

    # references
    refs_html = ""
    if doc.refs:
        items = "".join('<li id="ref-%s">%s</li>' % (safe_id(i), h) for i, h in doc.refs)
        refs_html = ('<section class="references" id="references" data-title="References">'
                     '<h2 id="references-start" data-sec="1" data-title="References" data-w="0" data-in="references" data-body="0">References</h2>'
                     '<details open><summary>%d references (citations in the text open these as cards)</summary><ol>%s</ol></details></section>') % (len(doc.refs), items)
        toc.append((2, "references", "References", 0))

    def chunk_ps(a):
        return re.sub(r"<p>(.*?)</p>", lambda m: "<p>%s</p>" % chunked(m.group(1), 40), a, flags=re.S)
    abstracts = "".join('<section class="abstract"><h2>%s</h2>%s</section>' % (esc(h), chunk_ps(a)) for h, a in doc.abstracts)
    total_words = sum(words(strip_tags(block_text(b))) for b in doc.blocks if b["t"] != "h")
    authors = m.get("authors") or []
    meta_bits = [x for x in [esc(m.get("venue") or ""), str(m.get("year") or "")] if x]
    doi = m.get("doi")
    if doi:
        meta_bits.append('<a href="https://doi.org/%s" rel="noopener">doi:%s</a>' % (attr(doi), esc(doi)))
    elif m.get("url"):
        meta_bits.append('<a href="%s" rel="noopener">%s</a>' % (attr(m["url"]), esc(m["url"])))
    meta_bits.append("about %d min of reading in the main text" % max(1, round(main_words(doc) / float(WPM))))
    why = ""
    if list_line:
        why = '<div class="why"><b>%s</b> %s</div>' % (esc(list_pos or "On your list"), list_line)

    alone = bool(m.get("standalone"))
    back = '<ol class="back"><li><a href="#top">↑ Back to the start</a></li>%s</ol>' % (
        "" if alone else '<li><a href="index.html">← All papers</a></li>')
    toc_html = '<div class="toc-head">Contents</div><ol>%s</ol>%s' % ("".join(
        '<li class="l%d"><a href="#%s"><span>%s</span><span class="mins">%s</span></a></li>' % (
            l, h, esc(t), ('<span aria-hidden="true">%d′</span><span class="sr">%d min</span>' % (mins, mins)) if mins else "")
        for l, h, t, mins in toc), back)

    title_text = strip_tags(m.get("title_html") or esc(m.get("title", ""))).strip()
    page = PAGE.format(
        title=esc(title_text), pid=attr(m.get("pid", "")),
        kicker=esc(" · ".join(x for x in [m.get("kicker")] if x) or "Reading copy"),
        title_html=m.get("title_html") or esc(m.get("title", "")),
        part=('<p class="part">%s</p>' % esc(m["part"])) if m.get("part") else "",
        authors=authors_html(authors), meta=" · ".join(meta_bits), why=why,
        abstracts=abstracts, body="\n".join(out), refs=refs_html, toc=toc_html,
        source=esc(doc.source), built=datetime.date.today().isoformat(),
        panel=PANEL, all_link="" if alone else ALL_LINK, done="" if alone else DONE_BOX)
    return page, total_words


ABBR = {"al", "e.g", "i.e", "eg", "ie", "fig", "figs", "eq", "eqs", "vs", "cf", "approx", "no", "nos", "pp", "p",
        "st", "dr", "mr", "ms", "mrs", "prof", "inc", "ltd", "jr", "sr", "etc", "ca", "vol", "ch", "sec", "tab", "ref", "refs"}


def chunks(h, target):
    """Split one paragraph of safe HTML into runs of whole sentences of about
    `target` words, cutting only between tags (never inside a citation, note
    or emphasis). Returns a list of HTML strings; joined, they are `h` again."""
    parts = re.split(r"(<[^>]+>)", h)
    cuts, depth, pos = [], 0, 0
    for seg in parts:
        if seg.startswith("<"):
            if not re.match(r"<(br|img)\b", seg):
                depth += -1 if seg.startswith("</") else (0 if seg.endswith("/>") else 1)
        elif depth == 0:
            for m in re.finditer(r"([.?!])([”\"’)]*)(\s+)", seg):
                before = seg[:m.start()]
                word = re.search(r"([\w.]+)$", before)
                w = word.group(1).lower() if word else ""
                if w in ABBR or re.fullmatch(r"[a-z]", w) or re.fullmatch(r"(?:[a-z]\.)+[a-z]", w):
                    continue  # et al. / e.g. / Fig. / an initial
                nxt = seg[m.end():m.end() + 1] or "<"
                if not (nxt.isupper() or nxt.isdigit() or nxt in "“\"‘'(<["):
                    continue
                cuts.append(pos + m.end())
        pos += len(seg)
    if not cuts:
        return [h]
    out, start, acc = [], 0, 0
    total = words(strip_tags(h))
    for c in cuts:
        piece = h[start:c]
        n = words(strip_tags(piece))
        rest = total - acc - n
        if n >= target * 0.6 and rest >= target * 0.5:
            out.append(piece)
            acc += n
            start = c
    out.append(h[start:])
    return out


def chunked(h, target=70):
    cs = chunks(h, target)
    if len(cs) == 1:
        return h
    return "".join('<span class="chunk">%s</span>' % c for c in cs)


def pdf_anchor(doc, b):
    if doc.pdf and b.get("pdf"):
        return '<a href="%s#page=%d" title="open this page of the PDF">p. %s</a>' % (
            attr(pdf_href(doc)), b["pdf"], esc(str(b["label"])))
    return None


def block_text(b):
    t = b["t"]
    if t in ("p", "eq", "h"):
        return b["html"]
    if t == "list":
        return " ".join(b["items"])
    if t == "pre":
        return b["text"]
    if t == "fig":
        return (b.get("caption") or "") + " " + (b.get("table") or "")
    return ""


def main_words(doc):
    n = 0
    for b in doc.blocks:
        if b["t"] == "h" and b.get("appendix"):
            break
        if b["t"] != "h":
            n += words(strip_tags(block_text(b)))
    return n


PANEL = """<div class="panel" id="panel" role="group" aria-label="Reading settings" hidden>
  <div class="row" role="group" aria-label="Theme"><span>Theme</span><span class="seg">
    <button data-pref="theme" data-val="auto">Auto</button><button data-pref="theme" data-val="light">Light</button>
    <button data-pref="theme" data-val="sepia">Sepia</button><button data-pref="theme" data-val="dark">Dark</button></span></div>
  <div class="row" role="group" aria-label="Font"><span>Font</span><span class="seg">
    <button data-pref="font" data-val="literata" style="font-family:Literata">Literata</button>
    <button data-pref="font" data-val="iowan" style="font-family:'Iowan Old Style'">Iowan</button>
    <button data-pref="font" data-val="charter" style="font-family:Charter">Charter</button>
    <button data-pref="font" data-val="sans">Sans</button></span></div>
  <div class="row" role="group" aria-label="Size"><span>Size</span><span class="seg">
    <button id="size-down" aria-label="smaller">A−</button><span id="size-now" style="padding:.2rem .3rem">20px</span>
    <button id="size-up" aria-label="larger">A+</button></span></div>
  <div class="row" role="group" aria-label="Line length"><span>Line length</span><span class="seg">
    <button data-pref="width" data-val="narrow">Narrow</button><button data-pref="width" data-val="medium">Medium</button>
    <button data-pref="width" data-val="wide">Wide</button></span></div>
  <div class="row" role="group" aria-label="Paragraphs"><span>Paragraphs</span><span class="seg">
    <button data-pref="para" data-val="short">Shorter</button><button data-pref="para" data-val="orig">As published</button></span></div>
  <div class="row" role="group" aria-label="Line spacing"><span>Line spacing</span><span class="seg">
    <button data-pref="lh" data-val="tight">1.4</button><button data-pref="lh" data-val="normal">1.5</button>
    <button data-pref="lh" data-val="loose">1.7</button></span></div>
  <div class="note">People read fastest in different fonts, and liking a font doesn't predict it (Wallace et al., 2022). It's worth trying each one for a page.</div>
</div>"""

ALL_LINK = '<a class="btn" href="index.html">All papers</a>'
DONE_BOX = '<div class="done-box">Reached the end? <button id="mark-done" type="button">Mark as finished</button> It shows on the list of papers.</div>'

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="lit-reader">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: file:; style-src 'self' 'unsafe-inline' file:; font-src data:; script-src 'self' file:">
<title>{title}</title>
<link rel="stylesheet" href="assets/fonts.css">
<link rel="stylesheet" href="assets/reader.css">
</head>
<body data-pid="{pid}">
<a class="skip" href="#text-start">Skip to the text</a>
<div class="bar">
  <button id="toc-toggle" type="button" aria-expanded="false" aria-controls="toc">☰ Contents</button>
  <span class="where" id="where"></span>
  {all_link}
  <button id="aa" type="button" aria-label="Reading settings" aria-expanded="false" aria-controls="panel">Aa</button>
</div>
<div class="progress" id="progress"></div>
{panel}
<div class="layout">
<nav class="toc" id="toc" aria-label="Contents">{toc}</nav>
<main id="text-start" tabindex="-1">
<header class="paper" id="top">
  <div class="kicker">{kicker}</div>
  <h1>{title_html}</h1>
  {part}
  {authors}
  <div class="meta">{meta}</div>
  {why}
</header>
{abstracts}
{body}
<div id="end-of-body"></div>
{refs}
{done}
<footer class="source">{source} Built {built}.</footer>
</main>
</div>
<script src="assets/reader.js"></script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Ledger, cache and list
# --------------------------------------------------------------------------

def ledger_meta(ledger, pid):
    ledger = LEDGERS.get(ledger, ledger)
    con = sqlite3.connect("file:%s?mode=ro" % Path(ledger).expanduser(), uri=True)
    con.row_factory = sqlite3.Row
    r = con.execute("select * from papers where pid=?", (pid,)).fetchone()
    con.close()
    if not r:
        raise ReaderError("%s is not in %s" % (pid, ledger))
    return {"pid": pid, "title": r["title"], "authors": [a.strip() for a in (r["authors"] or "").split(";") if a.strip()],
            "year": r["year"], "venue": r["venue"], "doi": r["doi"], "arxiv": r["arxiv"], "pmcid": r["pmcid"]}


def stem(pid):
    return re.sub(r"[^A-Za-z0-9._-]", "_", pid)


def cache_file(sub, pid, ext):
    d = LIT_CACHE / sub
    exact = d / (stem(pid) + ext)
    if exact.exists():
        return exact
    hits = sorted(d.glob(stem(pid) + "~*" + ext))
    return hits[0] if hits else None


def source_pdf(meta):
    """The PDF behind a page. Standalone builds never look in the lit.py cache."""
    if meta.get("standalone"):
        return meta.get("pdf_path")
    return cache_file("pdf", meta["pid"], ".pdf")


def source_text(meta):
    """The plain text a build is checked against."""
    if meta.get("standalone"):
        return meta.get("text_path")
    return cache_file("text", meta.get("pid", ""), ".txt")


def slug(meta):
    first = (meta["authors"][0].split()[-1] if meta["authors"] else "paper").lower()
    first = unicodedata.normalize("NFKD", first).encode("ascii", "ignore").decode() or "paper"
    title = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", meta["title"] or "").encode("ascii", "ignore").decode().lower())
    title = "-".join([w for w in title.split("-") if w][:4])
    return "%s-%s-%s" % (re.sub(r"[^a-z0-9]", "", first), meta.get("year") or "", title)


def list_entry(n):
    """The must-read line as written in the must-read file, minus the
    sentences about access, which are bookkeeping, not reading guidance."""
    if not PROJECT_READING or not PROJECT_READING.exists():
        return None
    text = PROJECT_READING.read_text(encoding="utf-8")
    sec = re.search(r"## Must-read list.*?\n(.*?)(?:\n## |\Z)", text, re.S)
    if not sec:
        return None
    m = re.search(r"^%d\. (.+)$" % n, sec.group(1), re.M)
    if not m:
        return None
    line = m.group(1)
    sents = re.split(r"(?<=[.)])\s+(?=[A-Z(])", line)
    keep = [s for s in sents if not re.match(r"(Open access|Paywalled|Full text held|\()", s)]
    line = " ".join(keep).strip()
    h = esc(line)
    h = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", h)
    h = re.sub(r"`([^`]+)`", r"<code>\1</code>", h)
    return h


# --------------------------------------------------------------------------
# Fetching (online)
# --------------------------------------------------------------------------

class NamedHostsOnly(urllib.request.HTTPRedirectHandler):
    """A redirect may not leave the hosts the fetch was allowed to reach."""

    def __init__(self, allowed_hosts):
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        p = urllib.parse.urlparse(newurl)
        if p.scheme != "https" or p.netloc not in self.allowed_hosts:
            raise ReaderError("refusing a redirect to %s" % p.netloc)
        return urllib.request.HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)


def http_get(url, allowed_hosts):
    p = urllib.parse.urlparse(url)
    if p.scheme != "https" or p.netloc not in allowed_hosts:
        raise ReaderError("refusing to fetch from %s" % p.netloc)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.build_opener(NamedHostsOnly(allowed_hosts)).open(req, timeout=60) as r:
            return r.read(), r.headers.get("Content-Type", "")
    except (urllib.error.URLError, OSError) as e:
        raise ReaderError("could not fetch %s: %s" % (url, e))


def image_kind(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def data_uri(data):
    k = image_kind(data)
    if not k:
        return None
    return "data:%s;base64,%s" % (k, base64.b64encode(data).decode())


def fetch_arxiv(aid, d):
    d.mkdir(parents=True, exist_ok=True)
    url = "https://arxiv.org/html/%s" % urllib.parse.quote(aid, safe="/.")
    body, ctype = http_get(url, {"arxiv.org"})
    if b"ltx_document" not in body:
        raise ReaderError("arXiv has no HTML version of %s (got %s)" % (aid, ctype))
    (d / "arxiv.html").write_bytes(body)
    (d / "arxiv.url").write_text(url)
    root = parse_html(body.decode("utf-8", "replace"))
    imgs = d / "img"
    imgs.mkdir(exist_ok=True)
    n = 0
    for img in root.findall(lambda x: x.tag == "img"):
        src = img.attrs.get("src", "")
        if not src or src.startswith("data:") or src.startswith("http"):
            continue
        full = urllib.parse.urljoin(url, src)
        name = safe_id(src)
        target = imgs / name
        if target.exists():
            continue
        try:
            data, _ = http_get(full, {"arxiv.org"})
        except ReaderError as e:
            print("  image failed: %s (%s)" % (src, e))
            continue
        if image_kind(data):
            target.write_bytes(data)
            n += 1
    print("fetched arXiv HTML for %s and %d images into %s" % (aid, n, d))


def fetch_jats(pmcid, d):
    d.mkdir(parents=True, exist_ok=True)
    body, _ = http_get("https://www.ebi.ac.uk/europepmc/webservices/rest/%s/fullTextXML" % pmcid, {"www.ebi.ac.uk"})
    (d / "jats.xml").write_bytes(body)
    imgs = d / "img"
    imgs.mkdir(exist_ok=True)
    n = 0
    try:
        z, _ = http_get("https://www.ebi.ac.uk/europepmc/webservices/rest/%s/supplementaryFiles?includeInlineImage=yes" % pmcid, {"www.ebi.ac.uk"})
        with zipfile.ZipFile(io.BytesIO(z)) as zf:
            for info in zf.infolist():
                name = os.path.basename(info.filename)
                if info.file_size > 30 * 1024 * 1024 or not re.match(r"^[\w.-]+\.(jpe?g|png|gif)$", name, re.I):
                    continue
                data = zf.read(info)
                if image_kind(data):
                    (imgs / name).write_bytes(data)
                    n += 1
    except (ReaderError, zipfile.BadZipFile) as e:
        print("  no figure bundle for %s (%s)" % (pmcid, e))
    print("fetched JATS XML for %s and %d images into %s" % (pmcid, n, d))


def cmd_fetch(a):
    meta = ledger_meta(a.ledger, a.pid)
    d = SRC / slug(meta)
    if a.route == "arxiv":
        fetch_arxiv(meta["arxiv"] or a.pid.split(":", 1)[-1], d)
    elif a.route == "jats":
        pmcid = meta["pmcid"] or a.pmcid
        if not pmcid:
            body, _ = http_get("https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&resultType=lite&query=DOI:%s"
                               % urllib.parse.quote(meta["doi"] or "", safe="/"), {"www.ebi.ac.uk"})
            res = json.loads(body.decode("utf-8"))["resultList"]["result"]
            pmcid = next((r.get("pmcid") for r in res if r.get("pmcid")), None)
        if not pmcid or not re.match(r"^PMC\d+$", pmcid):
            raise ReaderError("no PMC id for %s" % a.pid)
        fetch_jats(pmcid, d)


# --------------------------------------------------------------------------
# Route: arXiv HTML
# --------------------------------------------------------------------------

class ArxivInline(Inline):
    def rule(self, n):
        c = n.cls()
        if n.tag == "span" and "ltx_note" in c:
            if "ltx_role_footnote" in c:
                content = n.find(lambda x: "ltx_note_content" in x.cls())
                if content is None:
                    return ""
                for junk in content.findall(lambda x: x.cls() & {"ltx_note_mark", "ltx_note_type", "ltx_tag_note"}):
                    junk.kids = []
                return self.doc.note(self.run(content).strip())
            return ""
        if n.tag == "a" and "ltx_ref" in c:
            href = n.attrs.get("href", "")
            if href.startswith("#bib."):
                return self.doc.cite([href[1:].replace("bib.", "", 1)], self.run(n))
            if href.startswith("#"):
                return '<a href="#x-%s">%s</a>' % (safe_id(href[1:]), self.run(n))
        if n.tag == "span" and "ltx_text" in c:
            inner = self.run(n)
            if "ltx_font_italic" in c:
                return "<em>%s</em>" % inner
            if "ltx_font_bold" in c:
                return "<strong>%s</strong>" % inner
            if "ltx_font_typewriter" in c:
                return "<code>%s</code>" % inner
            return inner
        if c & {"ltx_acm_description", "ltx_bib_cited", "ltx_tag_bibitem"}:
            return ""
        return None


def arxiv_doc(meta, d):
    path = d / "arxiv.html"
    if not path.exists():
        raise ReaderError("no arXiv HTML; run fetch --route arxiv first")
    root = parse_html(path.read_text(encoding="utf-8"))
    art = root.find(lambda x: x.tag == "article" and "ltx_document" in x.cls()) or root
    doc = Doc(dict(meta))
    url = (d / "arxiv.url").read_text().strip() if (d / "arxiv.url").exists() else ""
    doc.meta["url"] = url
    doc.meta["kicker"] = "arXiv " + (meta.get("arxiv") or "")
    doc.source = "Text from arXiv's HTML version (%s), which arXiv labels experimental." % url
    ix = ArxivInline(doc)
    imgdir = d / "img"
    doc.pdf = source_pdf(meta)
    doc._crops = docling_crops(d, doc.pdf)
    t = art.find(lambda x: "ltx_title_document" in x.cls())
    if t is not None:
        doc.meta["title_html"] = ArxivInline(Doc({})).run(t).strip()

    ab = art.find(lambda x: "ltx_abstract" in x.cls())
    if ab is not None:
        paras = [ix.run(p).strip() for p in ab.findall(lambda x: x.tag == "p")]
        doc.abstracts.append(("Abstract", "".join("<p>%s</p>" % p for p in paras if p)))

    def heading(n, level, appendix):
        tag = n.find(lambda x: "ltx_tag" in x.cls())
        no = tag.text().strip() if tag is not None else ""
        if tag is not None:
            tag.kids = []
        txt = ix.run(n).strip()
        if no and not no.endswith("."):
            no = no  # "Appendix A" style tags keep their own form
        return dict(t="h", level=level, html=txt, no=no, appendix=appendix)

    def walk(n, depth, appendix):
        for k in n.children():
            c = k.cls()
            if k.tag in ("nav", "header", "footer") or c & {"ltx_page_navbar", "ltx_authors", "ltx_abstract", "ltx_dates",
                                                            "ltx_keywords", "ltx_pubnotes", "ltx_classification", "ltx_title_document",
                                                            "ltx_acknowledgements_x"}:
                continue
            if "ltx_bibliography" in c:
                for li in k.findall(lambda x: x.tag == "li" and "ltx_bibitem" in x.cls()):
                    rid = li.attrs.get("id", "").replace("bib.", "", 1)
                    blocks = [ix.run(b).strip() for b in li.findall(lambda x: "ltx_bibblock" in x.cls() and "ltx_bib_cited" not in x.cls())]
                    doc.refs.append((rid, " ".join(x for x in blocks if x)))
                continue
            if k.tag == "section":
                app = appendix or "ltx_appendix" in c
                h = k.find(lambda x: x.tag in ("h2", "h3", "h4", "h5", "h6") and x.parent is k)
                if h is not None:
                    level = {"h2": 2, "h3": 3, "h4": 4}.get(h.tag, 4)
                    blk = heading(h, level, app and not appendix)
                    blk["id"] = "x-" + safe_id(k.attrs.get("id", "")) if k.attrs.get("id") else None
                    if app and not appendix:
                        blk["appendix"] = True
                    doc.blocks.append(blk)
                walk(k, depth + 1, app)
                continue
            if k.tag in ("h2", "h3", "h4", "h5", "h6"):
                if k.parent is not None and k.parent.tag == "section":
                    continue  # handled with its section
                doc.blocks.append(heading(k, 4, False))
                continue
            if k.tag == "p":
                h = ix.run(k).strip()
                if h:
                    doc.add(t="p", html=h)
                continue
            if k.tag == "figure" and k.parent is not None and k.parent.tag == "figure":
                continue
            if k.tag == "figure":
                arxiv_figure(doc, ix, k, imgdir)
                continue
            if k.tag in ("ul", "ol"):
                items = []
                for li in k.children():
                    if li.tag != "li":
                        continue
                    for tg in li.findall(lambda x: "ltx_tag_item" in x.cls()):
                        tg.kids = []
                    items.append(ix.run(li).strip())
                doc.add(t="list", ordered=k.tag == "ol", items=items)
                continue
            if k.tag == "table" and c & {"ltx_equation", "ltx_equationgroup"}:
                maths = [math_html(mm) for mm in k.findall(lambda x: x.tag == "math")]
                tags = [x.text().strip() for x in k.findall(lambda x: "ltx_tag_equation" in x.cls())]
                doc.add(t="eq", html=" ".join(maths) + ("&emsp;" + esc(tags[0]) if tags else ""))
                continue
            if "ltx_listing" in c:
                lines = [ln.text().rstrip() for ln in k.findall(lambda x: "ltx_listingline" in x.cls())]
                doc.add(t="pre", text="\n".join(lines))
                continue
            walk(k, depth, appendix)

    walk(art, 0, False)
    return doc


def arxiv_figure(doc, ix, k, imgdir):
    def owner(c):
        p = c.parent
        while p is not None and p.tag != "figure":
            p = p.parent
        return p
    own = [c for c in k.findall(lambda x: x.tag == "figcaption") if owner(c) is k]
    panels = [c for c in k.findall(lambda x: x.tag == "figcaption") if owner(c) is not k]
    cap = own[-1] if own else (panels[0] if panels else None)  # with panels, the figure's own caption comes last
    panels = [c for c in panels if c is not cap]
    label, caption, alts = "", "", []
    if cap is not None:
        for desc in cap.findall(lambda x: "ltx_acm_description" in x.cls()):
            alts.append(desc.text().strip())
        tg = cap.find(lambda x: "ltx_tag" in x.cls())
        if tg is not None:
            label = tg.text().strip()
            tg.kids = []
        caption = " ".join(x for x in [ix.run(cap).strip()] + [ix.run(c).strip() for c in panels] if x)
    imgs = []
    for img in k.findall(lambda x: x.tag == "img"):
        f = imgdir / safe_id(img.attrs.get("src", ""))
        if f.exists():
            u = data_uri(f.read_bytes())
            if u:
                imgs.append((u, img.attrs.get("alt") or (alts[0] if alts else "")))
    table = ""
    tb = k.find(lambda x: x.tag == "table")
    if tb is not None:
        table = ix.one(tb)
    kind = "table" if "ltx_table" in k.cls() else "figure"
    fid = "x-" + safe_id(k.attrs.get("id", "")) if k.attrs.get("id") else None
    if not label and not caption and not imgs and not table:
        return
    page = find_pdf_page(doc, label)
    if not imgs and not table:
        # arXiv's converter lost this figure: use Docling's crop of it from the PDF
        crop = doc._crops.get(float_key(label)) if hasattr(doc, "_crops") else None
        if crop:
            imgs, page = [(crop[0], alts[0] if alts else "")], crop[1]
    doc.add(t="fig", kind=kind, id=fid, label=label, caption=caption, imgs=imgs, table=table, page=page)


def float_key(label):
    m = re.match(r"^\s*(Fig(?:ure)?|Table|TABLE|FIGURE)\.?\s*([\dA-Z]+)", label or "", re.I)
    if not m:
        return None
    return ("table" if m.group(1).lower().startswith("tab") else "figure", m.group(2))


def docling_crops(d, pdf):
    """{("figure", "3"): (data uri, pdf page)} for every captioned picture or
    table in this paper's Docling output, cropped from the PDF page."""
    out = {}
    js = sorted((d / "docling").glob("*.json"))
    if not js or not pdf:
        return out
    j = json.loads(js[0].read_text(encoding="utf-8"))
    page_h = {int(k): v["size"]["height"] for k, v in j.get("pages", {}).items()}
    for kind in ("pictures", "tables"):
        for item in j.get(kind, []):
            caps = " ".join(j["texts"][int(c["$ref"].split("/")[2])].get("text", "") for c in item.get("captions", []))
            key = float_key(caps)
            prov = (item.get("prov") or [{}])[0]
            if not key or key in out or not prov.get("page_no"):
                continue
            png = crop_png(pdf, prov["page_no"], docling_box(prov["bbox"], page_h.get(prov["page_no"], 792)), page_h.get(prov["page_no"], 792))
            u = data_uri(png) if png else None
            if u:
                out[key] = (u, prov["page_no"])
    return out


def docling_box(bb, page_h):
    """Docling bbox -> (l, t, r, b) in PDF points, origin bottom left."""
    if bb.get("coord_origin", "BOTTOMLEFT") == "BOTTOMLEFT":
        return (bb["l"], bb["t"], bb["r"], bb["b"])
    return (bb["l"], page_h - bb["t"], bb["r"], page_h - bb["b"])


def find_pdf_page(doc, label):
    """The PDF page whose text starts a line with this figure label."""
    if not label:
        return None
    txt = source_text(doc.meta)
    if not txt:
        return None
    pages = txt.read_text(encoding="utf-8", errors="replace").split("\f")
    pat = re.compile(r"^\s*" + re.escape(label.rstrip(".:")) + r"[.:]", re.M)
    for i, p in enumerate(pages):
        if pat.search(p):
            return i + 1
    return None


# --------------------------------------------------------------------------
# Route: JATS (Europe PMC)
# --------------------------------------------------------------------------

class JatsInline(Inline):
    def rule(self, n):
        if n.tag in ("name", "string-name") and n.find(lambda x: x.tag == "surname") is not None:
            sur = n.find(lambda x: x.tag == "surname").text().strip()
            giv = n.find(lambda x: x.tag == "given-names")
            return esc(sur + (" " + giv.text().strip() if giv is not None else ""))
        if n.tag == "xref":
            kind = n.attrs.get("ref-type")
            rid = n.attrs.get("rid", "")
            if kind == "bibr":
                return self.doc.cite(rid.split(), self.run(n))
            if kind in ("fig", "table", "sec", "disp-formula", "supplementary-material"):
                return '<a href="#j-%s">%s</a>' % (safe_id(rid.split()[0]) if rid else "", self.run(n))
            if kind == "fn":
                fn = self.doc._jats_fns.get(rid)
                if fn is not None:
                    return self.doc.note(self.run(fn).strip())
            return self.run(n)
        if n.tag in ("inline-formula", "disp-formula", "alternatives"):
            m = n.find(lambda x: x.tag == "math")
            return math_html(m) if m is not None else self.run(n)
        if n.tag in ("label",) and n.parent is not None and n.parent.tag in ("fig", "table-wrap", "ref"):
            return ""
        if n.tag == "title" and n.parent is not None and n.parent.tag == "caption":
            return self.run(n).strip() + " "  # the shared whitelist drops <title>, but here it is the caption's first line
        if n.tag == "ext-link":
            href = safe_href(n.attrs.get("href", ""))
            inner = self.run(n)
            return '<a href="%s" rel="noopener noreferrer">%s</a>' % (attr(href), inner) if href else inner
        return None


def structured_ref(ix, cit):
    """An element-citation has fields but no punctuation between them."""
    names = [ix.one(n).strip() for n in cit.findall(lambda x: x.tag in ("name", "string-name", "collab"))]
    fields = [ix.run(c).strip() for c in cit.children() if c.tag not in ("person-group", "name", "string-name", "collab")]
    return ". ".join(x for x in [", ".join(names)] + fields if x) + "."


def jats_doc(meta, d):
    path = d / "jats.xml"
    if not path.exists():
        raise ReaderError("no JATS XML; run fetch --route jats first")
    root = et_to_node(ET.parse(str(path)).getroot())
    doc = Doc(dict(meta))
    doc._jats_fns = {n.attrs.get("id"): n for n in root.findall(lambda x: x.tag == "fn") if n.attrs.get("id")}
    ix = JatsInline(doc)
    imgdir = d / "img"
    doc.pdf = source_pdf(meta)
    doc.meta["kicker"] = meta.get("venue") or "Article"
    doc.source = "Text from Europe PMC's full-text XML for this article; figures from Europe PMC's file bundle."
    art_meta = root.find(lambda x: x.tag == "article-meta")
    if art_meta is not None:
        t = art_meta.find(lambda x: x.tag == "article-title")
        if t is not None:
            doc.meta["title_html"] = ix.run(t).strip()
        for ab in art_meta.findall(lambda x: x.tag == "abstract"):
            title = ab.find(lambda x: x.tag == "title" and x.parent is ab)
            head = title.text().strip() if title is not None else "Abstract"
            paras = [ix.run(p).strip() for p in ab.findall(lambda x: x.tag == "p")]
            doc.abstracts.append((head, "".join("<p>%s</p>" % p for p in paras if p)))

    def walk(n, depth, appendix=False):
        for k in n.children():
            t = k.tag
            if t == "sec" and k.find(lambda x: x.tag == "ref-list") is not None and k.find(lambda x: x.tag == "p") is None:
                continue  # a section holding only the reference list, which has its own place on the page
            if t == "sec":
                title = k.find(lambda x: x.tag == "title" and x.parent is k)
                if title is not None:
                    doc.add(t="h", level=min(2 + depth, 4), html=ix.run(title).strip(), id="j-" + safe_id(k.attrs.get("id", "")) if k.attrs.get("id") else None,
                            appendix=appendix)
                walk(k, depth + 1)
            elif t == "p":
                # a <p> can hold a figure or table; pull those out after the text
                floats = [c for c in k.children() if c.tag in ("fig", "table-wrap", "disp-formula", "list")]
                for f in floats:
                    f.parent.kids = [x for x in f.parent.kids if x is not f]
                h = ix.run(k).strip()
                if h:
                    doc.add(t="p", html=h)
                for f in floats:
                    walk_one(f)
            elif t in ("fig", "table-wrap", "disp-formula", "list"):
                walk_one(k)
            elif t in ("supplementary-material",):
                cap = k.find(lambda x: x.tag == "caption")
                if cap is not None:
                    doc.add(t="p", html="<em>Supplementary material (not held locally):</em> " + ix.run(cap).strip())
            elif t in ("title", "label", "ref-list"):
                continue
            else:
                walk(k, depth, appendix)

    def walk_one(k):
        t = k.tag
        if t == "fig" or t == "table-wrap":
            label = k.find(lambda x: x.tag == "label" and x.parent is k)
            cap = k.find(lambda x: x.tag == "caption")
            imgs = []
            for g in k.findall(lambda x: x.tag == "graphic"):
                href = g.attrs.get("href", "")
                base = os.path.basename(href)
                f = next((imgdir / (base + e) for e in ("", ".jpg", ".jpeg", ".png", ".gif") if base and (imgdir / (base + e)).is_file()), None)
                if f is not None:
                    u = data_uri(f.read_bytes())
                    if u:
                        imgs.append((u, ""))
            table = ""
            tb = k.find(lambda x: x.tag == "table")
            if tb is not None:
                table = ix.one(tb)
            caption = ix.run(cap).strip() if cap is not None else ""
            foot = k.find(lambda x: x.tag == "table-wrap-foot")
            if foot is not None and ix.run(foot).strip():
                caption += ' <small class="tnote">%s</small>' % ix.run(foot).strip()
            doc.add(t="fig", kind="table" if t == "table-wrap" else "figure",
                    id="j-" + safe_id(k.attrs.get("id", "")) if k.attrs.get("id") else None,
                    label=label.text().strip() if label is not None else "",
                    caption=caption, imgs=imgs, table=table)
        elif t == "disp-formula":
            m = k.find(lambda x: x.tag == "math")
            doc.add(t="eq", html=math_html(m) if m is not None else ix.run(k))
        elif t == "list":
            items = [ix.run(li).strip() for li in k.children() if li.tag == "list-item"]
            doc.add(t="list", ordered=k.attrs.get("list-type") in ("order", "arabic", "alpha-lower", "roman-lower"), items=items)

    body = root.find(lambda x: x.tag == "body")
    if body is not None:
        if body.children() and body.children()[0].tag == "p":
            doc.add(t="h", level=2, html="Introduction", id="j-intro")
        walk(body, 0)
    back = root.find(lambda x: x.tag == "back")
    if back is not None:
        ack = back.find(lambda x: x.tag == "ack")
        if ack is not None:
            doc.add(t="h", level=2, html="Acknowledgments", appendix=True)
            for p in ack.findall(lambda x: x.tag == "p"):
                doc.add(t="p", html=ix.run(p).strip())
    for ref in root.findall(lambda x: x.tag == "ref"):  # usually in <back>, but some articles keep them in the body
        cit = ref.find(lambda x: x.tag in ("mixed-citation", "element-citation", "citation"))
        if cit is not None:
            doc.refs.append((ref.attrs.get("id", ""), structured_ref(ix, cit) if cit.tag == "element-citation" else ix.run(cit).strip()))
    fns = [f for f in root.findall(lambda x: x.tag == "fn" and x.parent is not None and x.parent.tag == "fn-group")]
    notes = root.findall(lambda x: x.tag == "author-notes")
    extra = [ix.run(f).strip() for f in fns] + [ix.run(fn).strip() for an in notes for fn in an.findall(lambda x: x.tag == "fn")]
    extra = [e for e in extra if e]
    if extra:
        first_app = not any(b.get("appendix") for b in doc.blocks)
        doc.add(t="h", level=2, html="Article notes", appendix=first_app)
        for e in extra:
            doc.add(t="p", html=e)
    return doc


# --------------------------------------------------------------------------
# Route: PDF via Docling
# --------------------------------------------------------------------------

def run_docling(pdf, d, pages=None):
    """Convert a private copy of the PDF, so Docling never touches the original."""
    (d / "in").mkdir(parents=True, exist_ok=True)
    (d / "docling").mkdir(exist_ok=True)
    src = d / "in" / "paper.pdf"
    if Path(pdf).resolve() != src.resolve():
        shutil.copyfile(str(pdf), str(src))
    exe = shutil.which("docling") or str(HOME / ".local" / "bin" / "docling")
    if not Path(exe).exists():
        raise ReaderError("PDFs need Docling: uv tool install docling --python 3.12")
    cmd = [exe, str(src), "--to", "json", "--image-export-mode", "placeholder", "--output", str(d / "docling")]
    if pages:
        cmd += ["--page-range", pages]  # one argument, "253-314"
    print("running Docling on %s ..." % Path(pdf).name)
    r = subprocess.run(cmd, cwd=str(d), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise ReaderError("Docling failed:\n" + r.stdout.decode("utf-8", "replace")[-1500:])
    print("Docling JSON in %s" % (d / "docling"))


def cmd_pdf_convert(a):
    meta = ledger_meta(a.ledger, a.pid)
    pdf = cache_file("pdf", meta["pid"], ".pdf")
    if not pdf:
        raise ReaderError("no cached PDF for %s" % a.pid)
    run_docling(pdf, SRC / slug(meta), a.pages)


def crop_png(pdf, page, bbox, page_h, dpi=170):
    """Render one region of one PDF page with pdftoppm. bbox is
    (l, t, r, b) in PDF points with the origin at the bottom left."""
    l, t, r, b = bbox
    scale = dpi / 72.0
    pad = 4
    x, y = max(0, int((l - pad) * scale)), max(0, int((page_h - t - pad) * scale))
    w, h = int((r - l + 2 * pad) * scale), int((t - b + 2 * pad) * scale)
    if w < 10 or h < 10:
        return None
    tmp = WORK / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    root = tmp / "crop"
    png = tmp / "crop.png"
    if png.exists():
        png.unlink()
    # pdftoppm 26 writes nothing when the output root is "-", so go through a file
    r_ = subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(dpi), "-x", str(x), "-y", str(y),
                         "-W", str(w), "-H", str(h), "-png", "-singlefile", "--", str(pdf), str(root)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if r_.returncode != 0 or not png.exists():
        return None
    data = png.read_bytes()
    png.unlink()
    return data


WATERMARK = re.compile(r"^(Downloaded from |Downloaded by |This article is protected by copyright|Copyright ©)", re.I)
DICT = None


def word_list():
    global DICT
    if DICT is None:
        p = Path("/usr/share/dict/words")
        DICT = set(w.strip().lower() for w in p.read_text(errors="ignore").splitlines()) if p.exists() else set()
    return DICT


def join_drop_cap(text):
    """'H uman' is a drop cap read as its own word; 'T cells' is not."""
    m = re.match(r"^([B-HJ-Z]) ([a-z]+)", text)
    if m:
        w = (m.group(1) + m.group(2)).lower()
        stems = [w, w[:-1] if w.endswith("s") else w, w[:-2] if w.endswith("ed") else w, w[:-1] if w.endswith("ed") else w,
                 w[:-3] if w.endswith("ing") else w, w[:-3] + "e" if w.endswith("ing") else w]
        if any(x in word_list() for x in stems):
            return m.group(1) + text[2:]
    return text


def dehyphen(a, b):
    """Join 'perspec-' + 'tives' when the result is a word."""
    word_list()
    m1, m2 = re.search(r"(\w+)-$", a), re.match(r"([a-z]+)", b)
    if m1 and m2:
        joined = (m1.group(1) + m2.group(1)).lower()
        if joined in DICT or (joined.rstrip("s") in DICT) or (joined[:-2] in DICT and joined.endswith("ed")):
            return a[:-1] + b
    return a + b


def docling_doc(meta, d, pages=None):
    js = sorted((d / "docling").glob("*.json"))
    if not js:
        raise ReaderError("no Docling output; run pdf-convert first")
    j = json.loads(js[0].read_text(encoding="utf-8"))
    doc = Doc(dict(meta))
    doc.pdf = source_pdf(meta)
    doc.meta["kicker"] = meta.get("venue") or "Article"
    doc.source = "Text converted from the PDF by Docling; figures and tables are images cropped from the PDF pages."
    page_h = {int(k): v["size"]["height"] for k, v in j.get("pages", {}).items()}
    offset = 0
    if pages and page_h and min(page_h) == 1:
        offset = int(pages.split("-")[0]) - 1  # only if Docling renumbered the range from 1

    def resolve(ref):
        kind, idx = ref["$ref"].split("/")[1], int(ref["$ref"].split("/")[2])
        return kind, j[kind][idx]

    # reading order: the body tree, flattening groups
    order = []

    def flatten(node):
        for ch in node.get("children", []):
            kind, item = resolve(ch)
            if kind == "groups":
                order.append(("group-start", item))
                flatten(item)
                order.append(("group-end", item))
            else:
                order.append((kind, item))
                if kind in ("pictures", "tables"):
                    continue  # captions are children; handled with the float
                flatten(item)
    flatten(j["body"])

    # a repository's cover sheet ("Please cite the original version ... Take down policy") is not the paper
    cover = set()
    by_page = {}
    for t in j.get("texts", []):
        pg = (t.get("prov") or [{}])[0].get("page_no")
        by_page.setdefault(pg, []).append(t.get("text") or "")
    for pg, txts in by_page.items():
        blob = " ".join(txts).lower()
        if pg and pg <= 2 and sum(k in blob for k in ("please cite the original version", "take down policy",
                                                       "general rights", "this is an electronic reprint",
                                                       "self-archived", "to cite this article", "submit your article to this journal",
                                                       "view related articles", "citing articles")) >= 2:
            cover.add(pg)
    names = set(re.sub(r"\W", "", a.lower()) for a in meta.get("authors") or [])
    venue = re.sub(r"\W", "", (meta.get("venue") or "").lower())

    printed = printed_page_numbers(j)
    in_refs, refs_raw = False, []
    last_page = None
    pending = None  # paragraph text waiting for its continuation
    list_items = None
    list_depth = 0  # a list inside a list joins the outer one
    caption_ids = set()
    for kind, item in order:
        if kind in ("pictures", "tables"):
            for c in item.get("captions", []):
                caption_ids.add(c["$ref"])

    total_words = sum(words(t.get("text") or "") for t in j.get("texts", []) if t.get("label") not in ("page_header", "page_footer"))
    deferred = []
    front_dropped = []
    seen_head = [False]
    chapter_pre = [None]

    def flush():
        nonlocal pending
        if pending is not None:
            doc.add(t="p", html=esc(pending))
            pending = None
        while deferred:
            doc.add(t="p", html="<small>%s</small>" % esc(deferred.pop(0)))

    def page_marker(p):
        nonlocal last_page
        if p and p != last_page:
            last_page = p
            label = printed.get(p) or str(p + offset)
            doc.add(t="page", label=label, pdf=p + offset)

    for kind, item in order:
        if kind == "group-start":
            if item.get("label") in ("list", "ordered_list"):
                if list_depth == 0:
                    flush()
                    list_items = []
                list_depth += 1
            continue
        if kind == "group-end":
            if list_depth and item.get("label") in ("list", "ordered_list"):
                list_depth -= 1
                if list_depth == 0:
                    if list_items:
                        doc.add(t="list", ordered=item.get("label") == "ordered_list", items=list_items)
                    list_items = None
            continue
        if item.get("self_ref") in caption_ids:
            continue
        label = item.get("label")
        prov = item.get("prov") or [{}]
        p = prov[0].get("page_no")
        if label in ("page_header", "page_footer") or p in cover:
            continue
        text = (item.get("text") or "").strip()
        if label in ("text", "paragraph", "list_item", "footnote", "caption", "section_header", "title", "formula", "code", "checkbox_selected", "checkbox_unselected", "reference"):
            if WATERMARK.match(text):
                continue
        if kind in ("pictures", "tables"):
            pnum = p
            caps = [resolve(c)[1].get("text", "") for c in item.get("captions", [])]
            cap_text = " ".join(caps).strip()
            lab = ""
            mm = re.match(r"^((?:Fig(?:ure)?|Table|TABLE|FIGURE)\.?\s*[\dA-Z]+[.:]?)\s*(.*)$", cap_text, re.S)
            if mm:
                lab, cap_text = mm.group(1), mm.group(2)
            imgs = []
            if pnum and doc.pdf:
                bb = prov[0]["bbox"]
                box = (bb["l"], bb["t"], bb["r"], bb["b"]) if bb.get("coord_origin", "BOTTOMLEFT") == "BOTTOMLEFT" else \
                    (bb["l"], page_h[pnum] - bb["t"], bb["r"], page_h[pnum] - bb["b"])
                png = crop_png(doc.pdf, pnum + offset, box, page_h.get(pnum, 792))
                u = data_uri(png) if png else None
                if u:
                    imgs.append((u, cap_text[:200]))
            if not imgs and not cap_text:
                continue
            bb = prov[0].get("bbox") or {}
            if not cap_text and (abs(bb.get("r", 0) - bb.get("l", 0)) < 120 or abs(bb.get("t", 0) - bb.get("b", 0)) < 80):
                continue  # logos and icons
            held = None
            if not cap_text and pending and len(pending) < 400 and CAPTION_LIKE.match(pending):
                cm = CAPTION_LIKE.match(pending)  # the caption above the float, left as a paragraph
                lab, cap_text, pending = cm.group(1), cm.group(2).strip(), None
            caption = esc(cap_text)
            gm = TABLE_NOTE_GLUED.search(pending) if (pending and kind == "tables") else None
            if gm:  # Docling sometimes glues a table note onto the sentence the table cuts
                pending = pending[:gm.start()]
                caption += ' <small class="tnote">%s</small>' % esc(gm.group(1).strip())
            if pending is not None and not re.search(r"[.!?:;”\"')\]]$", pending):
                held, pending = pending, None  # a sentence cut by the float: finish it after the float
            flush()
            page_marker(pnum)
            doc.add(t="fig", kind="table" if kind == "tables" else "figure", label=lab, caption=caption,
                    imgs=imgs, table="", page=(pnum + offset) if pnum else None)
            pending = held
            continue
        if not text or furniture(text, doc.meta.get("title")):
            continue
        last = doc.blocks[-1] if doc.blocks else None
        cm = CAPTION_LIKE.match(text)
        if cm and len(text) < 400 and last is not None and last["t"] == "fig" and not last.get("label") and not last.get("caption"):
            last["label"], last["caption"] = cm.group(1), esc(cm.group(2).strip())
            continue
        if last is not None and last["t"] == "fig" and len(text) < 600 and (
                re.match(r"(Notes?[:.]|Sources?:)\s", text) or (last.get("kind") == "table" and TABLE_NOTE.match(text))):
            last["caption"] += ' <small class="tnote">%s</small>' % esc(text)  # "NS: Not significant ...", "Note: ..."
            continue
        if (pending is None and last is not None and last["t"] == "fig" and last.get("caption")
                and not re.search(r"[.!?)]$", strip_tags(last["caption"]).strip()) and re.match(r"^[a-z(]", text)):
            last["caption"] = esc(dehyphen(strip_tags(last["caption"]).strip(), text)) if last["caption"].endswith("-") \
                else last["caption"] + " " + esc(text)  # a caption continued in the next column
            continue
        if label in ("section_header", "title") and re.sub(r"\W", "", text.lower()) in names | {venue}:
            continue  # an author's name or the journal's name set as a heading
        if label in ("section_header", "title"):
            flush()
            seen_head[0] = True
            if REFS_HEAD.match(text):
                in_refs = True
                continue
            if in_refs and refs_raw:
                in_refs = False
            page_marker(p)
            if re.fullmatch(r"(Chapter|CHAPTER|Part|PART) [\dIVX]+", text):
                chapter_pre[0] = text  # "Chapter 9" then "Restoring Trust": one heading
                continue
            if chapter_pre[0]:
                text, chapter_pre[0] = chapter_pre[0] + ": " + text, None
            lvl = 2 if (item.get("level") or 1) <= 1 else 3
            if text.isupper() and len(text) > 3:
                text = text[0] + text[1:].lower()
            # acknowledgments near the front of a book or thesis don't end the main text
            end_matter = bool(END_MATTER.match(text)) and not any(b.get("appendix") for b in doc.blocks) and (
                sum(words(strip_tags(block_text(b))) for b in doc.blocks) >= FRONT_MATTER_SHARE * total_words)
            doc.add(t="h", level=lvl, html=esc(text), appendix=end_matter)
            continue
        surnames = [a.split()[-1] for a in doc.meta.get("authors") or [] if a.split()]
        if not in_refs and p and p <= 2 and len(text) < 800 and len(surnames) >= 3 and sum(1 for s in surnames if s in text) >= 3:
            continue  # the author line, with affiliation marks; the header shows the authors
        if not seen_head[0] and len(text.split()) < 25 and not re.match(r"keywords\b", text, re.I) and (
                not re.search(r"[.?!]$", text) or "@" in text or re.search(r"10\.\d{4,}/", text)):
            front_dropped.append(text)  # front matter before the first heading: affiliations, article type, DOI lines
            continue
        if in_refs:
            mk = (item.get("marker") or "").strip()
            refs_raw.append((mk + " " + text) if re.fullmatch(r"\[?\d{1,3}[.\]]?", mk) else text)
            continue
        if label == "list_item" and list_items is not None:
            flush()
            list_items.append(esc(re.sub(r"^[•·\-–]\s*", "", text)))
            continue
        if label == "footnote" and last is not None and last["t"] == "fig" and last.get("kind") == "table" and (
                TABLE_NOTE.match(text) or re.search(r"\bp\s?[<=≤]\s?0?\.\d", text)):
            last["caption"] += ' <small class="tnote">%s</small>' % esc(text)
            continue
        if label == "footnote":
            deferred.append(text)  # after the paragraph it interrupts, not inside it
            continue
        if label == "formula":
            flush()
            doc.add(t="eq", html=esc(text))
            continue
        if label == "code":
            flush()
            doc.add(t="pre", text=text)
            continue
        # body text: join a paragraph broken by a column or page
        if pending is not None and (pending.endswith("-") or not re.search(r"[.!?:;”\"')\]]$", pending)) and re.match(r"^[a-z(]", text):
            pending = dehyphen(pending, text) if pending.endswith("-") else pending + " " + text
            if p != last_page:
                page_marker(p)  # the marker lands before the joined paragraph; close enough
            continue
        flush()
        page_marker(p)
        pending = join_drop_cap(text)
    flush()
    link_references(doc, refs_raw)
    if front_dropped:
        print("  dropped %d short lines before the first heading: %s" % (
            len(front_dropped), " | ".join(t[:40] for t in front_dropped)[:400]))
    return doc


FRONT_MATTER_SHARE = 0.25  # end matter can't begin before this share of the document's words
TABLE_NOTE = re.compile(r"^(Notes?[:.]\s|Sources?:\s|[A-Z][A-Za-z]{0,5}: [A-Z]?[a-z]|[*∗†‡]+\s?p\s?[<=≤])")
CAPTION_LIKE = re.compile(r"^((?:Fig(?:ure)?|Table|TABLE|FIGURE)\.?\s*[A-Z]?\d+(?:\.\d+)?[.:])\s*(.+)$", re.S)
TABLE_NOTE_GLUED = re.compile(r"(?<=[a-z,]) ((?:[A-Z]{1,5}: [a-z][a-z ,()-]{2,80}\.\s?)+)$")

FURNITURE = re.compile(
    r"^(research article( summary)?|research articles?|reports?|reviews?|perspectives?|artificial intelligence|"
    r"read the full article at|view the article online|permissions|use of this article is subject to.*|"
    r"cite this article as.*|downloaded from .*|this article is protected by copyright.*|"
    r"routledge|taylor & francis group|check for updates|open n? ?access)$", re.I)


def furniture(text, title):
    """Publisher page furniture: kicker labels, bare URLs, stray glyphs, and the
    title repeated on later pages."""
    t = text.strip()
    if len(t) <= 2 or FURNITURE.match(t) or re.fullmatch(r"(https?://|www\.|doi\.org/|science\.org/)\S+", t):
        return True
    if title:
        norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
        if norm(t) and norm(t) == norm(title):
            return True
    return False


END_MATTER = re.compile(r"^\s*(acknowledg|supplementary|funding|author contributions|competing interests|"
                        r"declaration|data (and materials )?availability|disclosure|conflicts? of interest|notes on contributors|editor'?s summary)", re.I)

REFS_HEAD = re.compile(r"^\s*(references(\s+and\s+notes)?|bibliography|works cited|literature cited)\s*$", re.I)


def link_references(doc, raw):
    """Turn the PDF's reference list into doc.refs and link the citations in
    the text: numbered "(19)" / "(5, 8-10)" style, or author-year style."""
    if not raw:
        return
    numbered = sum(1 for r in raw if re.match(r"^\s*\[?\d{1,3}[.\])]\s", r)) > len(raw) / 2
    if numbered:
        cur = None
        for r in raw:
            m = re.match(r"^\s*\[?(\d{1,3})[.\])]\s+(.*)$", r, re.S)
            if m:
                cur = [m.group(1), m.group(2)]
                doc.refs.append(cur)
            elif cur is not None:
                cur[1] = dehyphen(cur[1], r) if cur[1].endswith("-") else cur[1] + " " + r
        doc.refs = [(n, esc(t)) for n, t in doc.refs]
        known = set(n for n, _ in doc.refs)

        def numfix(m):
            parts = re.split(r"(\s*[,–-]\s*)", m.group(2))
            if not all(re.fullmatch(r"\d{1,3}", x) or re.fullmatch(r"\s*[,–-]\s*", x) for x in parts):
                return m.group(0)
            if not any(x in known for x in parts):
                return m.group(0)
            return m.group(1) + "".join(doc.cite([x], x) if x in known else x for x in parts) + m.group(3)
        pat = re.compile(r"([(\[])(\d{1,3}(?:\s*[,–-]\s*\d{1,3})*)([)\]])")
    else:
        # author-year: a reference starts with a capitalised surname and contains a year
        refs, cur = [], None
        for r in raw:
            # "Abbott, A. (1988)", "Ackerman B and Fishkin JS (2002)", "van der Meer TWG (2017)", "Yle News (2019)"
            starts = re.match(r"^(?:(?:[Vv]an|[Vv]on|[Dd]e|[Dd]er|[Dd]en|[Dd]u|[Ll]a|[Ll]e)\s+)*[A-ZÀ-Þ][\w'’-]*(?:,| [A-ZÀ-Þ]{1,4}\b| \(| and | [A-ZÀ-Þ][a-zà-ÿ]+ \()", r) \
                and re.search(r"\b(1[89]\d\d|20\d\d)[a-z]?\b", r[:200])
            if starts or cur is None:
                cur = [r]
                refs.append(cur)
            else:
                cur.append(r)
        keys = {}
        for i, parts in enumerate(refs):
            t = " ".join(parts)
            rid = "r%d" % (i + 1)
            doc.refs.append((rid, esc(t)))
            sur = re.match(r"^(?:(?:[Vv]an|[Vv]on|[Dd]e|[Dd]er|[Dd]en|[Dd]u|[Ll]a|[Ll]e)\s+)*([A-ZÀ-Þ][\w'’-]+)", t)
            yr = re.search(r"(1[89]\d\d|20\d\d)([a-z]?)", t)
            if sur and yr:
                keys.setdefault((sur.group(1).lower(), yr.group(1) + yr.group(2)), rid)

        def numfix(m):
            rid = keys.get((m.group(1).lower(), m.group(2)))
            return doc.cite([rid], m.group(0)) if rid else m.group(0)
        pat = re.compile(r"\b(?:(?:[Vv]an|[Vv]on|[Dd]e|[Dd]er|[Dd]en|[Dd]u|[Ll]a|[Ll]e)\s+)*([A-ZÀ-Ý][\w'’-]+)(?:\s+et al\.?|\s+(?:and|&amp;)\s+[A-ZÀ-Ý][\w'’-]+)?,?\s+\(?((?:1[89]|20)\d\d[a-z]?)\b")
    for b in doc.blocks:
        if b["t"] == "p":
            b["html"] = pat.sub(numfix, b["html"])
        elif b["t"] == "list":
            b["items"] = [pat.sub(numfix, x) for x in b["items"]]


def printed_page_numbers(j):
    """Printed page numbers from headers and footers, where they are bare numbers."""
    out = {}
    for t in j.get("texts", []):
        if t.get("label") in ("page_header", "page_footer"):
            s = (t.get("text") or "").strip()
            m = re.fullmatch(r"(?:Page\s+)?(\d{1,4})(?:\s+of\s+\d+)?", s)
            p = (t.get("prov") or [{}])[0].get("page_no")
            if m and p and p not in out:
                out[p] = m.group(1)
    return out


# --------------------------------------------------------------------------
# Coverage check
# --------------------------------------------------------------------------

def tokens(text):
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return re.findall(r"[a-z0-9]+", text)


def coverage(page_html, meta, pages=None):
    txt = source_text(meta)
    if not txt:
        print("  coverage: no source text to compare against")
        return
    raw = txt.read_text(encoding="utf-8", errors="replace")
    if pages:  # compare against the converted pages only (pdftotext separates pages with form feeds)
        lo, hi = (int(x) for x in pages.split("-"))
        raw = "\f".join(raw.split("\f")[lo - 1:hi])
    src = tokens(raw)
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page_html, flags=re.S)
    body = re.sub(r'<img[^>]*>', " ", body)
    got = tokens(strip_tags(body))
    cs, cg = Counter(src), Counter(got)
    hit = sum(min(n, cg[w]) for w, n in cs.items())
    print("  coverage: %.1f%% of the %d words in the %s reached the page" % (
        100.0 * hit / max(1, len(src)), len(src), meta.get("text_label", "cached text")))
    grams = set(tuple(got[i:i + 5]) for i in range(len(got) - 4))
    miss = [tuple(src[i:i + 5]) not in grams for i in range(len(src) - 4)]
    runs, i = [], 0
    while i < len(miss):
        if miss[i]:
            k = i
            while k < len(miss) and miss[k]:
                k += 1
            if k - i >= 25:
                runs.append((k - i, i))
            i = k
        else:
            i += 1
    runs.sort(reverse=True)
    for n, i in runs[:8]:
        print("    missing run of %d words: %s ..." % (n, " ".join(src[i:i + 18])))
    return runs


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def write_assets(out=None):
    a = (out or OUT) / "assets"
    a.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(HERE / "reader.css"), str(a / "reader.css"))
    shutil.copyfile(str(HERE / "reader.js"), str(a / "reader.js"))
    faces = []
    for style, f in (("normal", "literata-opsz-normal.woff2"), ("italic", "literata-opsz-italic.woff2")):
        p = FONTS / f
        if p.exists():
            faces.append("@font-face{font-family:'Literata';font-style:%s;font-weight:200 900;font-display:swap;"
                         "src:url(data:font/woff2;base64,%s) format('woff2');}" % (style, base64.b64encode(p.read_bytes()).decode()))
    (a / "fonts.css").write_text("/* Literata, SIL Open Font License, via @fontsource-variable/literata@5.3.0 */\n" + "\n".join(faces))


def build_one(pid, ledger, route, list_n=None, list_total=None, pages=None, part=None):
    meta = ledger_meta(ledger, pid)
    d = SRC / slug(meta)
    if route == "arxiv":
        doc = arxiv_doc(meta, d)
    elif route == "jats":
        doc = jats_doc(meta, d)
    elif route == "pdf":
        doc = docling_doc(meta, d, pages)
    else:
        raise ReaderError("unknown route %s" % route)
    doc.meta["part"] = part
    line = list_entry(list_n) if list_n else None
    pos = ("Must-read %d of %d" % (list_n, list_total)) if list_n and list_total else None
    page, total = render(doc, line, pos)
    write_assets()
    name = slug(meta) + ".html"
    (OUT / name).write_text(page, encoding="utf-8")
    print("wrote %s (%d words, %d references, %d notes)" % (OUT / name, total, len(doc.refs), doc.nnotes))
    coverage(page, meta, pages)
    return name


def load_list():
    if not LIST_FILE.exists():
        raise ReaderError("no %s" % LIST_FILE)
    return json.loads(LIST_FILE.read_text(encoding="utf-8"))


def cmd_build(a):
    lst = load_list() if LIST_FILE.exists() else {"lists": []}
    total, part = None, None
    for L in lst["lists"]:
        for it in L["items"]:
            if it["pid"] == a.pid and L.get("name") == "Must-read":
                total = len(L["items"])
                a.list_n = a.list_n or it.get("n")
                a.pages = a.pages or it.get("pages")
                part = it.get("part")
    build_one(a.pid, a.ledger, a.route, a.list_n, total, a.pages, part)
    cmd_index(a)


def cmd_all(a):
    lst = load_list()
    for L in lst["lists"]:
        for it in L["items"]:
            if it.get("route"):
                try:
                    build_one(it["pid"], it["ledger"], it["route"], it.get("n") if L["name"] == "Must-read" else None,
                              len(L["items"]), it.get("pages"), it.get("part"))
                except ReaderError as e:
                    print("skipped %s: %s" % (it["pid"], e))
    cmd_index(a)


def cmd_index(a):
    lst = load_list()
    write_assets()
    sections = []
    for L in lst["lists"]:
        rows = []
        for it in L["items"]:
            try:
                meta = ledger_meta(it["ledger"], it["pid"])
            except ReaderError:
                meta = {"title": it["pid"], "authors": [], "year": "", "venue": "", "pid": it["pid"]}
            name = slug(meta) + ".html" if meta.get("authors") is not None else ""
            exists = name and (OUT / name).exists()
            who = meta["authors"][0].split()[-1] + (" et al." if len(meta["authors"]) > 2 else (" and " + meta["authors"][1].split()[-1] if len(meta["authors"]) == 2 else "")) if meta["authors"] else ""
            desc = " · ".join(esc(x) for x in [who, str(meta.get("year") or ""), meta.get("venue") or "",
                                               (it.get("part") or "").split(":")[0]] if x)
            if exists:
                mins = ""
                html_ = (OUT / name).read_text(encoding="utf-8")
                mm = re.search(r"about (\d+) min of reading", html_)
                if mm:
                    mins = " · about %s min" % mm.group(1)
                title = '<a href="%s">%s</a>' % (attr(name), esc(meta["title"]))
                desc += mins
            else:
                title = esc(meta["title"])
                desc += " · " + esc(it.get("why_not") or "no reading copy yet")
            rows.append('<li class="%s" data-pid="%s"><span class="n">%s</span><span class="t">%s</span><span class="s"></span><span class="d">%s</span></li>' % (
                "" if exists else "nofile", attr(it["pid"]), esc(str(it.get("n", ""))), title, desc))
        sections.append('<section class="list"><h2>%s</h2><p class="listnote">%s</p><ol>%s</ol></section>' % (
            esc(L["name"]), esc(L.get("note", "")), "".join(rows)))
    page = INDEX.format(lists="\n".join(sections), built=datetime.date.today().isoformat(), panel=PANEL,
                        bar=esc(INDEX_TEXT["index_bar"]), kicker=esc(INDEX_TEXT["index_kicker"]),
                        note=esc(INDEX_TEXT["index_note"] + " ") if INDEX_TEXT["index_note"] else "")
    (OUT / "index.html").write_text(page, encoding="utf-8")
    print("wrote %s" % (OUT / "index.html"))


INDEX = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'self' 'unsafe-inline' file:; font-src data:; script-src 'self' file:">
<title>Reading list</title>
<link rel="stylesheet" href="assets/fonts.css">
<link rel="stylesheet" href="assets/reader.css">
</head>
<body class="index">
<div class="bar"><span class="where">{bar}</span><button id="aa" type="button" aria-label="Reading settings" aria-expanded="false" aria-controls="panel">Aa</button></div>
{panel}
<div class="layout"><main>
<header class="paper"><div class="kicker">{kicker}</div><h1>Reading list</h1>
<div class="meta">{note}Built {built}.</div></header>
{lists}
</main></div>
<script src="assets/reader.js"></script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Standalone mode: one paper, no ledger
# --------------------------------------------------------------------------

ARXIV_ID = r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?"
DOI_RE = r"10\.\d{4,9}/[^\s\"<>]+"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?format=json&resultType=core&pageSize=5&query="


def parse_input(text):
    """(kind, value) for a PDF path, arXiv ID or URL, DOI or DOI URL, PMCID or PMC URL."""
    t = text.strip()
    p = Path(t).expanduser()
    if p.is_file():
        return "pdf", p.resolve()
    if t.lower().endswith(".pdf") and not re.match(r"https?://", t, re.I):
        raise ReaderError("no such file: %s" % t)
    m = re.match(r"^(?:https?://)?(?:www\.|export\.)?arxiv\.org/(?:abs|pdf|html)/(%s)(?:\.pdf)?/?(?:[?#].*)?$" % ARXIV_ID, t, re.I)
    if m:
        return "arxiv", m.group(1)
    m = re.match(r"^arxiv:\s*(%s)$" % ARXIV_ID, t, re.I)
    if m or re.match(r"^%s$" % ARXIV_ID, t):
        return "arxiv", m.group(1) if m else t
    m = re.search(r"\b(PMC\d+)\b", t, re.I)
    if m and (t.upper() == m.group(1).upper() or re.match(r"^https?://([\w-]+\.)*(nih\.gov|europepmc\.org)/", t, re.I)):
        return "pmcid", m.group(1).upper()
    m = re.match(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?(%s)$" % DOI_RE, t, re.I)
    if m:
        doi = urllib.parse.unquote(m.group(1))
        a = re.match(r"^10\.48550/arxiv\.(%s)$" % ARXIV_ID, doi, re.I)
        return ("arxiv", a.group(1)) if a else ("doi", doi)
    raise ReaderError("not a PDF, arXiv ID, DOI or PMCID: %s" % text)


def clean_title(t):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t or ""))).strip().rstrip(".")


def arxiv_meta(aid):
    body, _ = http_get("https://export.arxiv.org/api/query?id_list=%s" % urllib.parse.quote(aid, safe="/.v"), {"export.arxiv.org"})
    e = ET.fromstring(body).find(ATOM + "entry")
    if e is None or e.find(ATOM + "published") is None:
        raise ReaderError("arXiv has no paper %s" % aid)
    return {"pid": "arxiv:" + aid, "title": clean_title(e.findtext(ATOM + "title")),
            "authors": [a.findtext(ATOM + "name").strip() for a in e.findall(ATOM + "author")],
            "year": int(e.findtext(ATOM + "published")[:4]), "venue": (e.findtext(ARXIV_NS + "journal_ref") or "").strip() or None,
            "doi": (e.findtext(ARXIV_NS + "doi") or "").strip() or None, "arxiv": aid, "pmcid": None}


def crossref_meta(doi):
    body, _ = http_get("https://api.crossref.org/works/%s" % urllib.parse.quote(doi, safe=""), {"api.crossref.org"})
    m = json.loads(body.decode("utf-8"))["message"]
    authors = [" ".join(x for x in (a.get("given"), a.get("family")) if x) or a.get("name", "") for a in m.get("author", [])]
    parts = ((m.get("issued") or {}).get("date-parts") or [[None]])[0]
    return {"pid": "doi:" + doi, "title": clean_title((m.get("title") or [""])[0]), "authors": [a for a in authors if a],
            "year": parts[0] if parts else None, "venue": clean_title((m.get("container-title") or [""])[0]) or None,
            "doi": doi, "arxiv": None, "pmcid": None}


def epmc_record(query):
    body, _ = http_get(EPMC + urllib.parse.quote(query, safe=""), {"www.ebi.ac.uk"})
    res = json.loads(body.decode("utf-8")).get("resultList", {}).get("result", [])
    return res[0] if res else None


def epmc_meta(r):
    authors = []
    for a in (r.get("authorList") or {}).get("author", []):
        name = " ".join(x for x in (a.get("firstName"), a.get("lastName")) if x) or a.get("collectiveName") or a.get("fullName")
        if name:
            authors.append(name)
    year = r.get("pubYear")
    return {"pid": "pmc:" + (r.get("pmcid") or r.get("id", "")), "title": clean_title(r.get("title")), "authors": authors,
            "year": int(year) if year and year.isdigit() else None,
            "venue": ((r.get("journalInfo") or {}).get("journal") or {}).get("title"),
            "doi": r.get("doi"), "arxiv": None, "pmcid": r.get("pmcid")}


def need_tool(name, why):
    if not shutil.which(name):
        raise ReaderError("%s needs poppler's %s (macOS: brew install poppler)" % (why, name))


def pdf_to_text(pdf, out):
    """pdftotext's reading of the PDF, or None without poppler."""
    if not shutil.which("pdftotext"):
        return None
    r = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
    return out if r.returncode == 0 and out.exists() else None


def on_first_page(title, first):
    norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    return bool(norm(title)) and norm(title)[:60] in norm(first)


def guess_title(pdf, first):
    r = subprocess.run(["pdfinfo", str(pdf)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60) if shutil.which("pdfinfo") else None
    m = re.search(r"^Title:\s*(.+)$", r.stdout.decode("utf-8", "replace"), re.M) if r and r.returncode == 0 else None
    t = m.group(1).strip() if m else ""
    if len(t.split()) >= 3 and not re.search(r"\.(pdf|docx?|tex|indd)$|microsoft word|untitled", t, re.I):
        return t
    for line in first.splitlines():
        line = line.strip()
        if len(line.split()) >= 4 and not re.search(r"https?:|doi|©|copyright|journal|vol\.|arxiv", line, re.I):
            return line
    return "Untitled paper"


def pdf_meta(pdf, text, key):
    """Metadata for a local PDF. An identifier printed on its first page is
    trusted only if the record it leads to has this PDF's title."""
    first = text.read_text(encoding="utf-8", errors="replace").split("\f")[0] if text else ""
    m = re.search(r"arXiv:\s*(%s)" % ARXIV_ID, first)
    if m:
        try:
            meta = arxiv_meta(m.group(1))
            if on_first_page(meta["title"], first):
                return meta
        except ReaderError:
            pass
    for raw in re.findall(DOI_RE, first):
        doi = raw.rstrip(".,;)]")
        try:
            meta = crossref_meta(doi)
        except (ReaderError, KeyError, ValueError):
            continue
        if on_first_page(meta["title"], first):
            return meta
    year = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", first)
    print("  no record found for this PDF: title guessed from its first page, authors left blank")
    return {"pid": "pdf:" + key, "title": guess_title(pdf, first), "authors": [], "year": int(year.group(1)) if year else None,
            "venue": None, "doi": None, "arxiv": None, "pmcid": None}


def jats_text(xml, out):
    """The article's own words, for the coverage check of a page built from XML."""
    skip = {"tex-math", "annotation", "annotation-xml", "graphic", "object-id", "label"}
    parts = []

    def walk(e):
        if local(e.tag) in skip:
            return
        parts.append(e.text or "")
        for c in e:
            walk(c)
            parts.append(c.tail or "")

    def outermost(e):  # a reference list inside the body must not be counted twice
        if local(e.tag) in ("article-title", "abstract", "body", "ref-list"):
            walk(e)
            parts.append("\n")
        else:
            for c in e:
                outermost(c)
    outermost(ET.parse(str(xml)).getroot())
    out.write_text(" ".join(parts), encoding="utf-8")
    return out


def identify(kind, value):
    """(metadata, work folder, local PDF or None) for one input."""
    pdf = None
    if kind == "pdf":
        data = value.read_bytes()
        if b"%PDF-" not in data[:1024]:
            raise ReaderError("%s is not a PDF" % value)
        key = hashlib.sha256(data).hexdigest()[:16]
        d = WORK / "standalone" / ("pdf-" + key)
        (d / "in").mkdir(parents=True, exist_ok=True)
        pdf = d / "in" / "paper.pdf"
        pdf.write_bytes(data)
        meta = pdf_meta(pdf, pdf_to_text(pdf, d / "paper.txt"), key)
    elif kind == "arxiv":
        meta = arxiv_meta(value)
    elif kind == "pmcid":
        r = epmc_record("PMCID:%s" % value)
        if not r:
            raise ReaderError("Europe PMC has no record of %s" % value)
        meta = epmc_meta(r)
        meta["pmcid"] = value
    else:
        try:
            meta = crossref_meta(value)
        except (ReaderError, KeyError, ValueError):
            r = epmc_record('DOI:"%s"' % value)
            if not r:
                raise ReaderError("neither Crossref nor Europe PMC has a record of %s" % value)
            meta = epmc_meta(r)
            meta["doi"] = value
    if kind != "pdf":
        d = WORK / "standalone" / safe_id(meta["pid"])
        d.mkdir(parents=True, exist_ok=True)
    meta["standalone"] = True
    return meta, d, pdf


def open_pmcid(meta):
    """The PMCID to fetch, if Europe PMC holds this paper's full text openly."""
    if meta.get("pmcid"):
        return meta["pmcid"]
    if not meta.get("doi"):
        return None
    try:
        r = epmc_record('DOI:"%s"' % meta["doi"])
    except ReaderError:
        return None
    if r and r.get("pmcid") and r.get("isOpenAccess") == "Y" and r.get("inEPMC") == "Y":
        return r["pmcid"]
    return None


def arxiv_pdf(aid, d):
    (d / "in").mkdir(parents=True, exist_ok=True)
    data, _ = http_get("https://arxiv.org/pdf/%s" % urllib.parse.quote(aid, safe="/.v"), {"arxiv.org"})
    if b"%PDF-" not in data[:1024]:
        raise ReaderError("arXiv did not return a PDF for %s" % aid)
    out = d / "in" / "paper.pdf"
    out.write_bytes(data)
    return out


def take_route(want, meta, d, pdf, pages):
    """A local PDF is used as given, because it may be a particular version of
    the paper. Otherwise, or with --route online, the best source comes first:
    arXiv HTML, then Europe PMC XML, then the PDF."""
    tried = []
    if want == "auto" and pdf is not None:
        order = ["pdf"]
        if meta.get("arxiv") or meta.get("doi"):
            print("  using your PDF. To try the online version of this paper instead, add --route online")
    elif want in ("auto", "online"):
        order = ["arxiv", "jats", "pdf"]
    else:
        order = [want]
    for route in order:
        try:
            if route == "arxiv" and meta.get("arxiv"):
                fetch_arxiv(meta["arxiv"], d)
                try:
                    copy = pdf or arxiv_pdf(meta["arxiv"], d)
                    meta["text_path"], meta["text_label"] = pdf_to_text(copy, d / "paper.txt"), "PDF's text"
                    meta["pdf_path"], meta["pdf_href"] = copy, "https://arxiv.org/pdf/%s" % meta["arxiv"]
                except ReaderError as e:
                    print("  coverage check unavailable: %s" % e)
                return "arxiv", arxiv_doc(meta, d)
            if route == "jats":
                pmcid = open_pmcid(meta)
                if pmcid:
                    fetch_jats(pmcid, d)
                    meta["text_path"], meta["text_label"] = jats_text(d / "jats.xml", d / "jats.txt"), "article's XML"
                    return "jats", jats_doc(meta, d)
            if route == "pdf":
                if pdf is None and meta.get("arxiv"):
                    pdf = arxiv_pdf(meta["arxiv"], d)
                if pdf is None:
                    continue
                need_tool("pdftoppm", "The PDF route")
                need_tool("pdftotext", "The PDF route")
                meta["pdf_path"], meta["pdf_href"] = pdf, "paper.pdf"
                meta["text_path"], meta["text_label"] = pdf_to_text(pdf, d / "paper.txt"), "PDF's text"
                if not sorted((d / "docling").glob("*.json")):
                    run_docling(pdf, d, pages)
                return "pdf", docling_doc(meta, d, pages)
        except ReaderError as e:
            tried.append("%s: %s" % (route, e))
            print("  %s route unavailable: %s" % (route, e))
    if want not in ("auto", "online") and not tried:
        raise ReaderError("the %s route doesn't apply to this input" % want)
    raise ReaderError("no open full text found. Download the PDF and run: lit-reader paper.pdf" + ("\n  " + "\n  ".join(tried) if tried else ""))


def cmd_standalone(a):
    if a.pages and not re.fullmatch(r"\d+-\d+", a.pages):
        raise ReaderError("--pages takes a range such as 12-30")
    kind, value = parse_input(a.input)
    meta, d, pdf = identify(kind, value)
    if a.pages:  # a page range is a different conversion of the same PDF
        d = d / ("pages-" + a.pages)
        d.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"-+", "-", slug(meta)).strip("-") or "paper"
    out = Path(a.output).expanduser() if a.output else Path.cwd() / name
    target = out / "index.html"
    ours = target.is_file() and 'content="lit-reader"' in target.read_text(encoding="utf-8", errors="replace")[:600]
    if out.exists() and (not out.is_dir() or (any(out.iterdir()) and not ours)):
        raise ReaderError("%s already holds other files; choose an empty folder with -o" % out)
    route, doc = take_route(a.route, meta, d, pdf, a.pages)
    page, total = render(doc)
    out.mkdir(parents=True, exist_ok=True)
    write_assets(out)
    if route == "pdf":
        shutil.copyfile(str(meta["pdf_path"]), str(out / "paper.pdf"))
    target.write_text(page, encoding="utf-8")
    print("wrote %s (route %s, %d words, %d references, %d notes)" % (target, route, total, len(doc.refs), doc.nnotes))
    coverage(page, doc.meta, a.pages)


LEDGER_COMMANDS = ("fetch", "pdf-convert", "build", "index", "all")


def standalone_parser():
    ap = argparse.ArgumentParser(prog="lit-reader", description="Turn one academic paper into an offline HTML reading copy.",
                                 epilog="Ledger commands: %s (each has its own --help)." % ", ".join(LEDGER_COMMANDS))
    ap.add_argument("--version", action="version", version="lit-reader " + __version__)
    ap.add_argument("input", help="a PDF path, arXiv ID or URL, DOI, or PMCID")
    ap.add_argument("-o", "--output", help="output folder (default: ./<slug>/)")
    ap.add_argument("--route", choices=["auto", "online", "arxiv", "jats", "pdf"], default="auto",
                    help="source to use. auto (default) keeps a local PDF as given and otherwise picks the best source; "
                         "online prefers arXiv or Europe PMC even when you supply a PDF")
    ap.add_argument("--pages", help="PDF route only: convert these pages, for example 12-30")
    return ap


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in LEDGER_COMMANDS:
        try:
            cmd_standalone(standalone_parser().parse_args(argv))
        except ReaderError as e:
            print("error: %s" % e, file=sys.stderr)
            return 1
        return 0
    ap = argparse.ArgumentParser(prog="lit-reader", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--pid", required=True)
    f.add_argument("--ledger", required=True)
    f.add_argument("--route", choices=["arxiv", "jats"], required=True)
    f.add_argument("--pmcid")
    c = sub.add_parser("pdf-convert")
    c.add_argument("--pid", required=True)
    c.add_argument("--ledger", required=True)
    c.add_argument("--pages")
    b = sub.add_parser("build")
    b.add_argument("--pid", required=True)
    b.add_argument("--ledger", required=True)
    b.add_argument("--route", choices=["arxiv", "jats", "pdf"], required=True)
    b.add_argument("--list-n", type=int)
    b.add_argument("--pages")
    sub.add_parser("index")
    sub.add_parser("all")
    a = ap.parse_args(argv)
    try:
        apply_settings()
        {"fetch": cmd_fetch, "pdf-convert": cmd_pdf_convert, "build": cmd_build, "index": cmd_index, "all": cmd_all}[a.cmd](a)
    except ReaderError as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
