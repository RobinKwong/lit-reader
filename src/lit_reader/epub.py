"""EPUB 3 export of a finished reading copy, for Kindles and other e-readers.

The EPUB is made from the page lit-reader has already built, so every route
gives the same result. The text is split into one file per top-level section.
Sidenotes become pop-up footnotes where the reader supports them, the original
page numbers become EPUB page breaks with a page list, and embedded images
become files in the book. Settings, buttons and links to the local PDF are left
out, because an e-reader has its own.
"""
import base64
import datetime
import hashlib
import os
import re
import uuid
import zipfile

from .core import Node, attr, esc, image_kind, parse_html, short_citation

XHTML_NS = "http://www.w3.org/1999/xhtml"
MATH_NS = "http://www.w3.org/1998/Math/MathML"
KEEP = {"p", "em", "strong", "i", "b", "sup", "sub", "span", "a", "ul", "ol", "li", "table", "thead", "tbody",
        "tfoot", "tr", "th", "td", "caption", "figure", "figcaption", "h2", "h3", "h4", "h5", "h6", "br", "hr",
        "small", "code", "pre", "blockquote", "div", "img", "cite", "q", "u", "s", "dl", "dt", "dd", "section"}
SKIP = {"button", "script", "style", "summary", "nav", "input", "link", "meta"}
VOID_OUT = {"br", "hr", "img"}
PLAIN_ATTRS = {"id", "href", "src", "alt", "colspan", "rowspan", "width", "height", "value", "start"}
BAD_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif"}

CSS = """body { margin: 0 4%; line-height: 1.5; }
body, p, li, h1, h2, h3, h4, td, th, figcaption { -webkit-hyphens: manual; -epub-hyphens: manual; adobe-hyphenate: none; hyphens: manual; }
h1 { font-size: 1.5em; line-height: 1.25; margin: 1em 0 .5em; }
h2 { font-size: 1.25em; margin: 1.6em 0 .5em; }
h3 { font-size: 1.1em; margin: 1.3em 0 .4em; }
h4 { font-size: 1em; font-style: italic; }
p { margin: 0 0 .8em; text-indent: 0; }
p.cont { margin-top: -.4em; }
.kicker, .meta, .source { font-size: .85em; }
.authors { font-weight: bold; }
div.pg { font-size: .75em; color: #777; text-align: right; margin: .2em 0; }
div.table-text { font-size: .85em; margin: 0 0 1.2em; }
figure { margin: 1.2em 0; }
figure img, .eq img { max-width: 100%; height: auto; }
figcaption { font-size: .85em; margin-top: .4em; }
table { border-collapse: collapse; font-size: .85em; margin: .8em 0; }
td, th { border: 1px solid #999; padding: .2em .4em; vertical-align: top; }
.eq { margin: .8em 0; text-align: center; }
aside { font-size: .9em; }
ol.refs li { margin-bottom: .4em; font-size: .9em; }
"""


def clean(text):
    return BAD_CHARS.sub("", text)


def fix_id(i):
    """An XML id must start with a letter."""
    i = re.sub(r"[^A-Za-z0-9_.-]", "-", i)
    return i if re.match(r"[A-Za-z_]", i) else "i" + i


class Book(object):
    def __init__(self, meta, bundle=None):
        self.meta = meta
        self.bundle = bundle or {}  # in a bundle's EPUB: each paper's page name -> (its folder, a label)
        self.images = {}       # sha -> (name, media type, bytes)
        self.where = {}        # id -> chapter file
        self.pages = []        # (file, id, label)

    def image(self, src):
        """Store a data-URI image and return its path in the book, or None."""
        if not src.startswith("data:"):
            return None
        try:
            data = base64.b64decode(src.split(",", 1)[1])
        except (IndexError, ValueError):
            return None
        kind = image_kind(data)
        if not kind:
            return None
        sha = hashlib.sha1(data).hexdigest()[:16]
        if sha not in self.images:
            self.images[sha] = ("images/%s.%s" % (sha, EXT[kind]), kind, data)
        return self.images[sha][0]


class Writer(object):
    """Serialises one chapter's nodes as XHTML."""

    def __init__(self, book, fname):
        self.book = book
        self.fname = fname
        self.notes = []

    def href(self, h):
        if h.startswith("#"):
            target = fix_id(h[1:])
            f = self.book.where.get(target)
            if f is None:
                return None
            return ("#" if f == self.fname else f + "#") + target
        if re.match(r"(?i)https?://|mailto:", h):
            return h
        return None  # local files (the PDF, the index page) aren't in the book

    def attrs(self, n, extra=""):
        out = []
        for k, v in n.attrs.items():
            if k == "id":
                out.append(' id="%s"' % attr(fix_id(v)))
            elif k in PLAIN_ATTRS and k not in ("href", "src"):
                out.append(' %s="%s"' % (k, attr(clean(v))))
        return "".join(out) + extra

    def kids(self, n):
        return "".join(self.node(k) for k in n.kids)

    def math(self, n, root=False):
        if isinstance(n, str):
            return esc(clean(n))
        a = "".join(' %s="%s"' % (k, attr(clean(v))) for k, v in n.attrs.items()
                    if not k.startswith(("on", "data-")) and k not in ("style", "class") and re.fullmatch(r"[a-z][a-z-]*", k))
        if root:
            a = ' xmlns="%s"' % MATH_NS + a
        inner = "".join(self.math(k) for k in n.kids)
        return "<%s%s>%s</%s>" % (n.tag, a, inner, n.tag) if inner else "<%s%s/>" % (n.tag, a)

    def node(self, n):
        if isinstance(n, str):
            return esc(clean(n))
        t, c = n.tag, n.cls()
        if t in SKIP:
            return ""
        if t == "math":
            return self.math(n, root=True)
        if "sn-mark" in c:
            target = fix_id(n.attrs.get("data-for", ""))
            shown = esc(clean(n.text().strip()))
            return '<sup><a epub:type="noteref" href="#%s" id="nref-%s">%s</a></sup>' % (target, target, shown)
        if "sidenote" in c:
            num = n.find(lambda x: "n" in x.cls())
            shown = num.text().strip() if num is not None else ""
            if num is not None:
                num.kids = []
            self.notes.append((fix_id(n.attrs.get("id", "")), shown, self.kids(n)))
            return ""
        if "pg" in c and t == "span":
            pid = fix_id(n.attrs.get("id", "pg"))
            label = clean(n.text().strip())
            self.book.pages.append((self.fname, pid, re.sub(r"^p\.\s*", "", label)))
            return '<div class="pg" epub:type="pagebreak" role="doc-pagebreak" id="%s" title="%s">%s</div>' % (
                pid, attr(re.sub(r"^p\.\s*", "", label)), esc(label))
        if t == "details" and "orig-page" in c:
            s = n.find(lambda x: x.tag == "summary")
            name = re.sub(r"^Show the original page \((.*)\)$", r"\1", s.text().strip()) if s is not None else "page"
            img = n.find(lambda x: x.tag == "img")
            src = self.book.image(img.attrs.get("src", "")) if img is not None else None
            if not src:
                return ""
            return ('<figure><img src="%s" alt="%s"/><figcaption>The original %s, as printed. Some text on this page '
                    'may not have come through.</figcaption></figure>') % (src, attr("The original " + name), esc(name))
        if t == "details" and "table-text" in c:  # keep its label: the summary is dropped like every summary
            s = n.find(lambda x: x.tag == "summary")
            return '<div class="table-text"><p><strong>%s</strong></p>%s</div>' % (
                esc(s.text().strip() if s is not None else "Table as text"), self.kids(n))
        if "in-bundle" in c:  # a reference that is another paper of the bundle
            a = n.find(lambda x: x.tag == "a")
            to = self.book.bundle.get(a.attrs.get("href", "")) if a is not None else None
            if not to:  # a paper's own EPUB has no other paper to go to
                return ""
            return ' <em>In this book: <a href="../%s/title.xhtml">%s</a></em>' % (attr(to[0]), esc(to[1]))
        if t == "a":
            if "pdf-link" in c:
                return ""
            h = self.href(n.attrs.get("href", ""))
            inner = self.kids(n)
            return '<a href="%s">%s</a>' % (attr(h), inner) if h else inner
        if t == "img":
            src = self.book.image(n.attrs.get("src", ""))
            if not src:
                return ""
            return '<img src="%s" alt="%s"%s/>' % (src, attr(clean(n.attrs.get("alt", ""))), "".join(
                ' %s="%s"' % (k, attr(n.attrs[k])) for k in ("width", "height") if re.fullmatch(r"\d+", n.attrs.get(k, ""))))
        if t == "p" and any(isinstance(k, Node) and "chunk" in k.cls() for k in n.kids):
            parts = [self.kids(k) if isinstance(k, Node) and "chunk" in k.cls() else self.node(k) for k in n.kids]
            parts = [p for p in parts if p.strip()]
            return "".join('<p%s>%s</p>' % (self.attrs(n) if i == 0 else ' class="cont"', p) for i, p in enumerate(parts))
        if "tablewrap" in c or t == "details" or ("chunk" in c and t == "span"):
            return self.kids(n)
        if t not in KEEP:
            return self.kids(n)
        if t in VOID_OUT:
            return "<%s/>" % t
        keep_cls = ' class="eq"' if "eq" in c else ""
        return "<%s%s>%s</%s>" % (t, self.attrs(n, keep_cls), self.kids(n), t)

    def chapter(self, nodes):
        body = "".join(self.node(k) for k in nodes)
        if self.notes:
            body += '<section epub:type="footnotes">%s</section>' % "".join(
                '<aside epub:type="footnote" id="%s"><p><a href="#nref-%s">%s</a> %s</p></aside>' % (i, i, esc(s), h)
                for i, s, h in self.notes)
        return body


def xhtml(title, body):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="%s" xmlns:epub="http://www.idpf.org/2007/ops" lang="en" xml:lang="en">\n'
            '<head><meta charset="utf-8"/><title>%s</title><link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
            '<body>%s</body>\n</html>\n') % (XHTML_NS, esc(clean(title)), body)


def section_title(h):
    return clean((h.attrs.get("data-title") or h.text()).strip()) or "Section"


def build(page_html, meta, bundle=None):
    """(files, toc) for a finished page: files maps path in the book to bytes."""
    root = parse_html(page_html)
    main = root.find(lambda x: x.tag == "main")
    if main is None:
        raise ValueError("not a lit-reader page")
    book = Book(meta, bundle)
    title = clean(meta.get("title") or "Untitled paper")

    head = main.find(lambda x: x.tag == "header")
    front = []
    if head is not None:
        for k in head.children():
            if "au-toggle" in k.cls() or k.tag == "button":
                continue
            for b in k.findall(lambda x: x.tag == "button"):
                b.kids = []
            for h in k.findall(lambda x: "au-rest" in x.cls()):
                h.attrs.pop("hidden", None)
            front.append(k)

    chapters = []       # (file, title, nodes)
    refs = None
    cur = None
    for k in main.children():
        c = k.cls()
        if k.tag == "header" or k.tag == "footer" or "done-box" in c or k.attrs.get("id") == "end-of-body":
            continue
        if "abstract" in c:
            front.append(k)
            continue
        if "references" in c:
            refs = k
            continue
        if k.tag == "h2" or cur is None:
            carry = []  # a page that starts with this heading belongs to its chapter, not the end of the last one
            while cur is not None and cur[2] and ("pg" in cur[2][-1].cls() or "orig-page" in cur[2][-1].cls()):
                carry.insert(0, cur[2].pop())
            cur = ("ch%02d.xhtml" % (len(chapters) + 1), section_title(k) if k.tag == "h2" else "Text", carry)
            chapters.append(cur)
        cur[2].append(k)
    if len(chapters) > 1 and chapters[0][1] == "Text":
        lead = " ".join(n.text() for n in chapters[0][2] if "pg" not in n.cls() and "orig-page" not in n.cls())
        if len(lead.split()) < 30:  # only a page number before the first heading: no chapter of its own
            f, t, nodes = chapters[1]
            chapters = [(chapters[0][0], t, chapters[0][2] + nodes)] + chapters[2:]
            chapters = [("ch%02d.xhtml" % (i + 1), t, nodes) for i, (_, t, nodes) in enumerate(chapters)]

    # where each id lives, so links can cross files
    plan = [("title.xhtml", title, front)] + chapters
    for f, _, nodes in plan:
        for n in nodes:
            for d in n.iter():
                for key in ("id",):
                    if d.attrs.get(key):
                        book.where[fix_id(d.attrs[key])] = f
                if "sn-mark" in d.cls():
                    book.where["nref-" + fix_id(d.attrs.get("data-for", ""))] = f
    if refs is not None:
        for d in refs.iter():
            if d.attrs.get("id"):
                book.where[fix_id(d.attrs["id"])] = "refs.xhtml"

    files = {}
    w = Writer(book, "title.xhtml")
    kicker = head.find(lambda x: "kicker" in x.cls()) if head is not None else None
    t_html = head.find(lambda x: x.tag == "h1") if head is not None else None
    parts = ['<p class="kicker">%s</p>' % w.kids(kicker) if kicker is not None else "",
             '<h1>%s</h1>' % (w.kids(t_html) if t_html is not None else esc(title))]
    for k in front:
        if k.tag in ("h1",) or "kicker" in k.cls():
            continue
        if "abstract" in k.cls():
            parts.append(w.kids(k))
        else:
            cls = [x for x in ("authors", "meta", "part") if x in k.cls()]
            inner = w.kids(k)
            if inner.strip():
                parts.append('<p%s>%s</p>' % (' class="%s"' % cls[0] if cls else "", inner))
    foot = main.find(lambda x: x.tag == "footer")
    if foot is not None:
        parts.append('<p class="source">%s Converted to EPUB by lit-reader.</p>' % w.kids(foot))
    files["title.xhtml"] = xhtml(title, "".join(parts) + w.chapter([]))

    for f, t, nodes in chapters:
        w = Writer(book, f)
        files[f] = xhtml(t, w.chapter(nodes))
    toc = [("title.xhtml", title)] + [(f, t) for f, t, _ in chapters]
    if refs is not None:
        w = Writer(book, "refs.xhtml")
        items = refs.findall(lambda x: x.tag == "li")
        body = '<h2>References</h2><ol class="refs">%s</ol>' % "".join("<li%s>%s</li>" % (w.attrs(li), w.kids(li)) for li in items)
        files["refs.xhtml"] = xhtml("References", body + w.chapter([]))
        toc.append(("refs.xhtml", "References"))

    files["nav.xhtml"] = xhtml("Contents", (
        '<nav epub:type="toc" id="toc"><h2>Contents</h2><ol>%s</ol></nav>' % "".join(
            '<li><a href="%s">%s</a></li>' % (f, esc(t)) for f, t in toc)) + (
        '<nav epub:type="page-list" hidden="hidden"><h2>Pages</h2><ol>%s</ol></nav>' % "".join(
            '<li><a href="%s#%s">%s</a></li>' % (f, i, esc(l)) for f, i, l in book.pages) if book.pages else ""))
    files["style.css"] = CSS
    for name, kind, data in book.images.values():
        files[name] = data
    return files, toc


def identifier(meta):
    if meta.get("doi"):
        return "urn:doi:" + meta["doi"]
    if meta.get("arxiv"):
        return "urn:arxiv:" + meta["arxiv"]
    return "urn:uuid:%s" % uuid.uuid5(uuid.NAMESPACE_URL, "lit-reader:" + str(meta.get("pid") or meta.get("title")))


def opf(meta, files, toc):
    media = {"xhtml": "application/xhtml+xml", "css": "text/css", "png": "image/png", "jpg": "image/jpeg", "gif": "image/gif"}
    items, spine = [], []
    order = [f for f, _ in toc]
    for n, name in enumerate(sorted(files)):
        ext = name.rsplit(".", 1)[-1]
        props = []
        if name == "nav.xhtml":
            props.append("nav")
        if ext == "xhtml" and "<math" in files[name]:
            props.append("mathml")
        items.append('<item id="f%d" href="%s" media-type="%s"%s/>' % (
            n, attr(name), media[ext], ' properties="%s"' % " ".join(props) if props else ""))
    ids = dict((name, "f%d" % n) for n, name in enumerate(sorted(files)))
    spine = "".join('<itemref idref="%s"/>' % ids[f] for f in order)
    creators = "".join('<dc:creator>%s</dc:creator>' % esc(clean(a)) for a in (meta.get("authors") or []))
    date = '<dc:date>%s</dc:date>' % meta["year"] if meta.get("year") else ""
    modified = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="en">\n'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="uid">%s</dc:identifier><dc:title>%s</dc:title>%s%s<dc:language>en</dc:language>'
            '<meta property="dcterms:modified">%s</meta></metadata>\n'
            '<manifest>%s</manifest>\n<spine>%s</spine>\n</package>\n') % (
        esc(identifier(meta)), esc(clean(meta.get("title") or "Untitled paper")), creators, date, modified,
        "".join(items), spine)


CONTAINER = ('<?xml version="1.0" encoding="utf-8"?>\n'
             '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
             '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>'
             '</container>\n')


def write_epub(page_html, meta, path):
    files, toc = build(page_html, meta)
    return write_zip(files, opf(meta, files, toc), path)


def write_bundle(built, title, note, path, missing=()):
    """One book of several papers. `built` is a list of (page html, meta, page
    name). Each paper keeps its own files in a folder of its own (p01/, p02/,
    ...), so its links and images work as in its own EPUB; a contents page
    comes first, and the contents nest each paper's sections under it."""
    bundle = {}
    for i, (_, meta, name) in enumerate(built, 1):
        bundle[name] = ("p%02d" % i, short_citation(meta))  # the paper as it's cited: "Tessler et al., 2024"
    files, spine, nav, listing = {}, [], [], []
    for page, meta, name in built:
        folder = bundle[name][0]
        try:
            pf, toc = build(page, meta, bundle)
        except ValueError as e:
            print("  left out of the bundle EPUB: %s (%s)" % (meta.get("title"), e))
            continue
        for f, data in pf.items():
            if f != "nav.xhtml":
                files[folder + "/" + f] = data
        spine += [folder + "/" + f for f, _ in toc]
        t = clean(meta.get("title") or "Untitled paper")
        nav.append('<li><a href="%s/title.xhtml">%s</a><ol>%s</ol></li>' % (folder, esc(t), "".join(
            '<li><a href="%s/%s">%s</a></li>' % (folder, f, esc(st)) for f, st in toc[1:])))
        who = ", ".join(clean(a) for a in (meta.get("authors") or [])[:3]) + (" et al." if len(meta.get("authors") or []) > 3 else "")
        listing.append('<li><a href="%s/title.xhtml">%s</a>%s</li>' % (
            folder, esc(t), esc(" · " + ", ".join(x for x in (who, str(meta.get("year") or "")) if x)) if who or meta.get("year") else ""))
    if not spine:
        raise ValueError("no paper could be added")
    gone = ('<p class="meta">Not included, because %s couldn\'t be converted: %s.</p>' % (
        "it" if len(missing) == 1 else "they", "; ".join(esc(clean(m)) for m in missing)) if missing else "")
    files["index.xhtml"] = xhtml(title, '<h1>%s</h1>%s<ol>%s</ol>%s<p class="source">Made by lit-reader.</p>' % (
        esc(clean(title)), '<p class="meta">%s</p>' % esc(clean(note)) if note else "", "".join(listing), gone))
    files["style.css"] = CSS
    files["nav.xhtml"] = xhtml("Contents", '<nav epub:type="toc" id="toc"><h2>Contents</h2><ol>%s</ol></nav>' % "".join(nav))
    book = {"title": title, "authors": [], "pid": "bundle:" + "|".join(str(m.get("pid")) for _, m, _ in built)}
    return write_zip(files, opf(book, files, [(f, "") for f in ["index.xhtml"] + spine]), path)


def write_zip(files, package, path):
    part = str(path) + ".part"  # a failure leaves no half-written book where an e-reader would take it
    with zipfile.ZipFile(part, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", package, compress_type=zipfile.ZIP_DEFLATED)
        for name, data in sorted(files.items()):
            z.writestr("OEBPS/" + name, data, compress_type=zipfile.ZIP_DEFLATED)
    os.replace(part, str(path))
    return path
