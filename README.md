# lit-reader

lit-reader turns an academic paper into an offline HTML reading copy, with reflowed text, a contents sidebar, citation cards, sidenotes and a saved reading position.

![A paper in lit-reader, with a citation card open beside the text and a contents sidebar showing the minutes in each section](docs/screenshot.png)

<sub>Shown: Setälä, Christensen, Leino and Strandberg, "Beyond polarization and selective trust", *Politics* (2021), doi:10.1177/02633957211024474, CC BY-NC.</sub>

## Why lit-reader

Most academic papers are published as PDFs laid out for print, which makes them hard work to read on a laptop. lit-reader is for researchers, students, journalists and anyone else who reads papers closely on a screen. It resets the paper for long reading and keeps the authors' words as they wrote them, with no AI summaries or rewriting.

PDF viewers show you the printed page. lit-reader reflows the text and adds the tools you need while reading. A search of PyPI in November 2026 found no other package that combines reflowed text with these tools:

- **Text set for reading.** Lines run to about 65 characters, and lit-reader adds no automatic hyphenation. Long paragraphs are split at sentence ends, and an "As published" setting restores the original breaks.
- **Citations that open in place.** Click a citation to read the reference in a card without losing your place. Footnotes sit in the margin.
- **A sense of where you are.** The contents sidebar shows the minutes in each section, the top bar shows the time left, and the page reopens where you stopped. Papers built from a PDF also keep their original page numbers in the margin.
- **Settings for your own eyes.** You can change the theme, font, size, line length and line spacing. People read fastest in different fonts, and [liking a font doesn't predict which one](https://research.adobe.com/publication/towards-individuated-reading-experiences-different-fonts-increase-reading-speed-for-different-individuals).
- **A check on every build.** lit-reader reports the share of the source's words that reached the page and lists any long passages that didn't. Tables and figures from a PDF appear as images, so their words count as missing.
- **Private and offline.** Each reading copy is a local HTML page that loads nothing from the network and needs no account or server.

## Install

lit-reader needs [uv](https://docs.astral.sh/uv/). To try it without installing anything permanently:

```
uvx --from git+https://github.com/RobinKwong/lit-reader lit-reader 2401.04088
```

To install the `lit-reader` command:

```
uv tool install git+https://github.com/RobinKwong/lit-reader
```

Papers with an arXiv HTML version or open-access text in Europe PMC need nothing else. To read PDFs, also install [poppler](https://poppler.freedesktop.org/) and [Docling](https://github.com/docling-project/docling):

```
brew install poppler                     # Debian or Ubuntu: sudo apt install poppler-utils
uv tool install docling --python 3.12
```

Docling downloads about 2 GB of models the first time it runs. lit-reader has only been tested on macOS so far.

## Usage

```
lit-reader paper.pdf
lit-reader 2401.04088
lit-reader https://arxiv.org/abs/2401.04088
lit-reader 10.1371/journal.pmed.0020124
lit-reader PMC1182327
```

The reading copy is written to `./<slug>/index.html`, where the slug combines the first author, year and title. Open that file in a browser. Keep the folder together, because the page uses the `assets` folder beside it.

| Option | What it does |
|---|---|
| `-o DIR` | Writes the reading copy to `DIR` instead. |
| `--route ROUTE` | Chooses the source, as described in the next section. |
| `--pages A-B` | Converts only these pages of a PDF, for example `--pages 12-30`. |

## Which source is used

**If you give a PDF, lit-reader reads that PDF.** Your file may be a particular version of the paper, such as an accepted manuscript, so it is never replaced by an online copy without your asking.

**If you give an identifier**, lit-reader uses the best source it can find: arXiv's HTML, then Europe PMC's full-text XML for open-access papers, then arXiv's PDF.

To change this, use `--route`:

| Option | What it does |
|---|---|
| `--route auto` | The default, as described above. |
| `--route online` | Prefers arXiv's HTML or Europe PMC's XML, even when you give a PDF. If neither is available, it falls back to your PDF. |
| `--route arxiv` | Uses arXiv's HTML only. |
| `--route jats` | Uses Europe PMC's XML only. |
| `--route pdf` | Uses the PDF only. |

For example, `lit-reader paper.pdf --route online` looks for an online version of the paper in your PDF. It can only do this if the PDF's first page shows an arXiv ID or a DOI.

Even with the default route, lit-reader sends an arXiv ID or DOI found on a PDF's first page to arXiv or Crossref to look up the title and authors. The PDF itself is never uploaded.

### What each source gives you

| Source | Best for | What to expect |
|---|---|---|
| arXiv HTML | Recent arXiv papers | Real headings, linked citations and live tables. arXiv labels this format experimental, and some figures don't convert. The page links to the PDF for those. |
| Europe PMC XML | Open-access papers in Europe PMC | Real headings, linked citations and the publisher's figures. |
| PDF | Everything else | Text converted by Docling, with the original page numbers in the margin. Figures and tables are images cropped from the page. |

## What it works with

lit-reader is tuned for academic papers, and it also handles other long PDFs with selectable text, such as dissertations and reports. A 370-page dissertation took about two minutes to convert on a Mac laptop.

- **Formats:** it accepts PDFs, arXiv IDs or URLs, DOIs and PMCIDs. It doesn't accept EPUB, Word, HTML, plain text or links to web articles.
- **DOIs:** a DOI only works when arXiv or Europe PMC has the full text openly available. For a book or a paywalled paper, supply the PDF.
- **Headings:** the contents sidebar depends on headings that look different from the body text. A plainly typeset manuscript may come through as one long section.
- **Scanned PDFs:** Docling recognises the text, but the coverage check can't run because the PDF has no text to compare against.
- **Citations and footnotes:** citation cards need a reference list that lit-reader can recognise. In PDFs, footnotes appear as small text after the paragraph instead of in the margin.
- **Languages:** accented Latin text comes through correctly, but pages are marked as English and line-break repair uses an English word list. Right-to-left scripts and Chinese, Japanese and Korean are untested.

## Checking a reading copy

Every build compares the page with the source text and prints the result:

```
coverage: 95.6% of the 5438 words in the PDF's text reached the page
  missing run of 58 words: the proportion of repeated layer 0 0 20 0 15 ...
```

A missing run is a stretch of 25 or more source words that didn't reach the page. Runs of numbers and labels usually come from charts and tables, which is expected when they appear as images. A run of ordinary sentences means text was lost, so check that passage against the original.

Pages built from arXiv HTML or a PDF are compared with the PDF's text, which needs poppler. Pages built from Europe PMC are compared with the article's XML.

## Copyright

Reading copies are for your own use. The MIT licence below covers this software, not the papers you convert, which keep their own copyright and licences. Please don't redistribute reading copies of paywalled papers. A reading copy made from a PDF includes a copy of that PDF in its folder, so take particular care when sharing one.

## Licence

lit-reader is released under the [MIT licence](LICENSE).
