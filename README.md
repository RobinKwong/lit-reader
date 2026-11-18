# lit-reader

lit-reader turns an academic paper into an offline HTML reading copy, with reflowed text, a contents sidebar, citation cards, sidenotes and a saved reading position.

## Usage

```
lit-reader paper.pdf
lit-reader 2401.04088
lit-reader https://arxiv.org/abs/2401.04088
lit-reader 10.1371/journal.pmed.0020124
lit-reader PMC1182327
```

The reading copy is written to `./<slug>/index.html`. Use `-o DIR` to choose another folder.

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

PDFs need [Docling](https://github.com/docling-project/docling) and [poppler](https://poppler.freedesktop.org/).
