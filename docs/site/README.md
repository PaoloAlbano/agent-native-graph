# Documentation site sources

The HTML templates, CSS, and JavaScript in this folder are editable sources for
the research website. The catalog is generated from the effective native tool
specifications and decorator metadata in the Python package. `example.json`
selects one archived run/QID and contains editorial guide notes. Its tool
arguments and responses are read verbatim from `results/`; the build verifies
the run checksum against its manifest.

From the repository root:

```bash
make docs-build
make docs-serve
```

Open `http://127.0.0.1:8000`. Override the local port with `DOCS_PORT=8001`.

`make docs-build` also runs `social_preview.py` to add static Open Graph and
Twitter card metadata to every generated page, using `ana-social-preview.png`.
The image reproduces the header wordmark and is copied to the published assets.
Titles and descriptions come from each page; image and page URLs are absolute.
For a fork or custom domain, pass `DOCS_PUBLIC_URL=https://example.org/project/`.
The lower-level `build-docs` CLI generates the research content only; use Make
for the complete deployable site, as CI does. Preview changes become available
after publishing; sharing platforms may cache an earlier preview.

The build writes generated HTML, assets, JSON projections and `.nojekyll` into
the ignored `build/site/` directory, both locally and in CI. `docs/` contains
only public Markdown and editable site sources. It is not the output directory.
The Markdown documentation and benchmark evidence remain intact. GitHub Actions
assembles and deploys the generated artifact. No database, inference endpoint,
or API key is needed to build. Override `DOCS_OUT` for another build directory;
`make docs-serve` serves that same directory.

The entry point `.github/workflows/ci.yml` runs on every branch push, pull request
and manual invocation: lint/format first, then Python and browser tests. Successful
code checks call the reusable `.github/workflows/docs.yml` builder. On feature
branches and PRs this is **Check Documentation Build**, without artifact upload
or deployment. On `main` it is **Build Release Documentation**, followed by artifact
upload and **Publish GitHub Pages**. The test job needs neither the comparison
checkout nor model/database secrets; only the builder checks out the pinned source.
Select **GitHub Actions** as the Pages source in repository
settings. CI builds into `build/site/` so only generated public site artifacts
are uploaded. Editorial Markdown files remain available through repository links.

To contribute a Company run, add its complete archive (`manifest.json`,
`summary.json`, `failures.jsonl`, `run.jsonl`, `run-config.json`) under
`results/cypherbench-company/full/runs/<unique-run-id>/` and open a pull request.
Runs that enabled before/after graph verification must also include the
checksummed `graph-integrity.json`. Missing, unverified or inconsistent evidence
is rejected before presentation; historical archives without that opt-in feature
keep their original file layout. See [block verification](../reproduction.md#beforeafter-graph-block-verification).
The workflow validates and builds the site without publishing from pull requests.
After merge to `main`, the complete CI pipeline rebuilds and publishes Pages
automatically if all checks pass. No hand
editing of generated HTML or model lists is needed. New models without matching
external baselines remain visible under ANA results; comparison availability is
reported explicitly instead of blocking the site build. A historical saved
query evaluation is not silently extended to new ANA runs.

New runs should use [the frozen run workflow](../run-standard.md) and also carry
`run-config.json`; its checksum and profile consistency are checked during the
build. Historical four-file archives remain supported without invented metadata.

Section 1 documents the current tool surface. Section 2 is a static multipage
site: `results.html` lists models, `model-*.html` lists a model's runs, and
`run-*.html` analyzes one run. Overview and model pages have no JavaScript,
question tables or JSON fetches. Ordinary links navigate between pages.
Only run pages load the explorer, with filters, tool traces and optional
per-question comparisons with another run.
Question URLs retain run selections and QID so individual analyses can be shared.
Run labels include temperature, reasoning and a stable short run identifier,
not a launch date. The identifier derives from the unchanged archive ID, so
repeated profiles remain distinguishable without renaming files or breaking
links. Original dates stay in downloadable provenance, not navigation labels.
The results index has
an overview generated from all validated archives, with a per-model observed
score range and retained run count; ranges are not pooled means or confidence
intervals. Historical generations and shared-preflight smoke diagnostics remain
separate. The overview requires no additional client-side data download.
The explorer displays
all 347 questions in a full-width table, with QID-only search and outcome filters.
Inspecting a row expands a single question inline, rather than using a narrow
scrolling sidebar. Closed JSON disclosures do not serialize or mount their
contents. Open previews are capped at 20,000 characters and removed on close;
the complete, unchanged record remains available through the download link.
The browser caches at most two fetched JSON payloads.
Historical run contracts must be identified
by their source revision rather than inferred from the current catalog.

The example exposes recorded tool responses and clickable handle previews.
Full internal handle state and model reasoning text are not present in the
archive; editorial notes must never be presented as recorded model reasoning.

## Results data flow

Benchmark writers continue to save to `results/cypherbench-company/full/runs/`.
`research/docs_results.py` reads those archives without modifying them. The build
checks SHA-256, 347 unique QIDs, identical questions/gold across runs, and summary
counts/call means. Inconsistent evidence fails the build, rather than silently
changing scores or omitting a run.

The general index contains only run metadata and links. Compact question
summaries live in a separate index for each run; only the active run's index
loads initially, plus a comparison index if explicitly selected. Each
full question record is exported unchanged into a separate JSON file, fetched
only when selected. The UI can compare two runs by QID, and link input handles
back to the recorded responses that created them. These are archived previews,
not reconstructed full server state. Raw JSON remains downloadable.

Generated files belong to the static presentation, not the benchmark archive;
do not commit or manually edit them. CI uses a clean output directory. A local
rebuild after removing a run may leave unreferenced generated JSON files; the
new index only lists currently validated runs.

## External Comparison

`comparison-source.json` pins the external Git revision. `make docs-build` uses
`REFERENCE_REPO` (default `../multigraphrag`); CI checks out the pinned revision.
Generated `comparison.html`, `comparison-*.html`, `assets/comparison.js` and
`data/comparison/` present only matched Company profiles on the pinned 100 QIDs.
Overview/profile pages require no JavaScript. A question page fetches only its
ANA record and the corresponding direct/agentic records and call logs.

Question comparisons render ANA's recorded execution inline using the same
trajectory renderer as the full-run explorer: ordered tools, arguments, output
summaries, clickable input-handle lineage and bounded response disclosures.
Technical failure is distinguished from an executed answer mismatch. Empty
transcripts explicitly explain missing steps; a zero-tool JSON parsing failure
must not look like an unexplained empty graph result. Failed response text is
not reconstructed when the archive does not contain it. The full-run question
link retains the QID and scrolls/focuses its expanded evidence after loading.

The source repo is read through Git objects, not mutable local files. No data is
written into `results/`. Missing source evidence is explicit, never replaced by
invented scores. Original exact-answer and LLM-judge verdicts are kept separate;
see [the comparison protocol](../multigraphrag-comparison.md) for limitations.

The separate common-metric table reads committed query-reexecution evidence,
not a fresh database query during build. It measures baseline query-result
correctness using ANA's exact comparator, not final textual-answer judging.
The loader accepts both standalone JSONLs and compact `storage.json` indices
with shared gzip packs; reconstructed bytes must match original manifest hashes.
The build remains offline. See [evidence storage](../../results/README.md) for
the layout, migration and standalone export commands.
