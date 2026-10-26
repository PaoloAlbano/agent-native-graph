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

The build writes `docs/index.html`, `docs/results.html`, `docs/model-*.html`,
`docs/run-*.html`, the site/results CSS and
JavaScript under `docs/assets/`, `docs/data/tool-catalog.json`,
`docs/data/example-trajectory.json`, `docs/data/results/`, and `docs/.nojekyll`.
It leaves the Markdown documentation and benchmark evidence intact. Generated
files are ignored locally; GitHub Actions assembles and deploys the Pages
artifact. No database, inference endpoint, or API key is needed to build.

The workflow `.github/workflows/docs.yml` validates pull requests and publishes
pushes to `main`. Select **GitHub Actions** as the Pages source in repository
settings. CI builds into `build/site/` so only generated public site artifacts
are uploaded. Editorial Markdown files remain available through repository links.

To contribute a Company run, add its complete archive (`manifest.json`,
`summary.json`, `failures.jsonl`, `run.jsonl`) under
`results/cypherbench-company/full/runs/<unique-run-id>/` and open a pull request.
The workflow validates and builds the site without publishing from pull requests.
After merge to `main`, it rebuilds and publishes Pages automatically. No hand
editing of generated HTML or model lists is needed. New models without matching
external baselines remain visible under ANA results; comparison availability is
reported explicitly instead of blocking the site build. A historical saved
query evaluation is not silently extended to new ANA runs.

Section 1 documents the current tool surface. Section 2 is a static multipage
site: `results.html` lists models, `model-*.html` lists a model's runs, and
`run-*.html` analyzes one run. Overview and model pages have no JavaScript,
question tables or JSON fetches. Ordinary links navigate between pages.
Only run pages load the explorer, with filters, tool traces and optional
per-question comparisons with another run.
Question URLs retain run selections and QID so individual analyses can be shared.
Run labels explicitly include temperature and reasoning. The explorer displays
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

The source repo is read through Git objects, not mutable local files. No data is
written into `results/`. Missing source evidence is explicit, never replaced by
invented scores. Original exact-answer and LLM-judge verdicts are kept separate;
see [the comparison protocol](../multigraphrag-comparison.md) for limitations.
