# Changelog

## v1.3

v1.3 shows how far you've got with each paper in a bundle.

- **Reading progress.** The index shows how much of each paper's main text you've read ("About 40% read", with a bar) and when you last read it ("3 days ago"). Only time spent reading counts: opening a paper or jumping to its conclusion adds nothing, and skimming barely moves the figure. Papers you opened with an earlier version of lit-reader show "In progress" until you read some more of them. Like the rest of the index, it has been checked in Chrome only.
- **A shorter settings panel on the index.** It offers only theme, font and size, the settings that change the list.

## v1.2

v1.2 reads several papers as one set.

- **Bundles.** `lit-reader bundle <file>` builds every paper listed in a text file into one folder, with an index page showing which papers you've started or finished and how many quotes you've saved from each. A paper that can't be converted is listed with the reason and what to do, and the rest are still built.
- **Moving between papers.** Each paper's top bar shows its place in the bundle ("3 of 7"). A citation of another paper in the bundle links to its reading copy, and that paper's bar then offers the way back to the citation.
- **Quotes across the bundle.** The index downloads or copies every saved quote as one Markdown file, grouped by paper with each one's citation.
- **One EPUB for the bundle.** `--epub bundle` writes one book holding every paper, with the bundle's contents first and references between its papers linked. `--epub both` also writes one EPUB per paper.
- **A thinner bar on a phone.** The top bar holds only the contents button and the reading status, and steps aside as you scroll down. All papers, Quotes and the reading settings sit at the top of the contents drawer.
- **Smaller changes.** "Finished" on the index now has enough contrast in every theme, and marking a paper finished is announced to screen readers.

## v1.1

v1.1 takes the reading copies off the laptop, onto a phone or an e-reader, and lets you keep quotes from what you read.

- **Reading on a phone.** Pages lay out for a phone screen. Citations open in a sheet along the bottom, the contents sit in a drawer, buttons are sized for touch, and tapping a figure or table opens it full screen.
- **Copies to take with you.** `--epub` writes an EPUB for Apple Books or another e-reader. `--single-file` writes the reading copy as one HTML file that survives being emailed and still shows its text where no script runs. `--email` sends either copy to you through your own mail account, and `lit-reader setup-email` sets that up.
- **Saved quotes.** Select a passage and save it with its author, year and page, then copy it or download all your quotes as Markdown. A tip on your first few papers points out the feature, the Quotes panel and the end of the paper remind you of quotes you haven't downloaded, and a removed quote can be restored until the panel closes.
- **More of the paper, and a check on what's missing.** When arXiv has no HTML version of a paper, lit-reader tries ar5iv's conversion before the PDF. Where a PDF page lost ordinary sentences, the reading copy offers that page as printed. Under each table from a PDF, an unchecked text version helps screen readers and small screens.
- **Cleaner PDF conversions.** A footnote that runs over a page break is joined back together, a numbered list of affiliations no longer splits the paragraph around it, and a summary in run-in labels (Science's "INTRODUCTION:", "RATIONALE:" and so on) gets its own heading in the contents, with an "Introduction" heading where the untitled article begins.
- **Smaller changes.** On a laptop, the Contents button hides the sidebar. Clicking a citation whose card is already showing goes on to the reference list. "Go to reference list" leaves a button back to where you were, and the contents show "6 min" rather than "6′". "Mark as finished" sits where the main text ends, before any appendix and the references. EPUBs aren't hyphenated, to match the reading copies.

## v1.0

The first public release, on 18 November 2026, first numbered 0.1.0. It turns a PDF, arXiv ID or URL, DOI or PMCID into an offline reading copy from arXiv's HTML, Europe PMC's XML or the PDF. The copy has reflowed text, a contents sidebar with the minutes in each section, citation cards, sidenotes, the printed page numbers, reading settings and a saved reading position. Each build reports how much of the source's text reached the page.
