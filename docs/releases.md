# Release Wheel and Docker Image

The release workflow is prepared, but adding it does **not** publish a package
or create a release. The first release must be explicitly published by a
maintainer after reviewing the dry run. This prototype is not a production
security certification.

## Deliverables

For a stable tag such as `v0.1.0`, the workflow produces:

| Location | Artifact |
| --- | --- |
| GitHub Release | `agent_native_graph-0.1.0-py3-none-any.whl` |
| GitHub Release | `agent_native_graph-0.1.0.tar.gz` (source distribution) |
| GitHub Release | `SHA256SUMS` (the wheel and source hashes) |
| GitHub Release | `image-digest.txt` (the published GHCR digest) |
| GHCR | `ghcr.io/paoloalbano/agent-native-graph:0.1.0` |

There is no automatic PyPI upload, `latest` tag or moving minor-version alias.
Only stable `vX.Y.Z` releases are supported in this first workflow. Prerelease
events cannot publish. The Python wheel is pure Python for Python 3.11+;
the container currently targets **Linux amd64 only**, not a multi-architecture
image. On Apple Silicon it needs amd64 emulation. Native arm64 release support
requires its own tested build before we advertise it.

## Maintainer Procedure

1. Update `project.version` in `pyproject.toml` for a new release and run
   `uv lock` to update the local package version in `uv.lock`. Keep both files
   in the PR. For the initial release, both already specify `0.1.0`.
2. Run the local checks below, then choose **Actions > Release artifacts > Run
   workflow** on your feature branch, with `tag=v0.1.0` (or the new version).
   This input validates the checked-out branch; it does not fetch or create a
   tag. A manual run **never publishes**, even on `main`.
3. Review the workflow, its checks and downloadable `python-distributions`
   artifact. Merge the reviewed code into `main` only after checks pass.
4. In GitHub Releases, create a release using a new `vX.Y.Z` tag on the reviewed
   `main` commit. Publish it explicitly. That `release: published` event runs
   the build/tests again on the tagged code and then publishes the tested
   artifacts. This upload-based workflow cannot handle already-immutable
   releases and rejects them before building or publishing any artifacts:
   assets are attached after the published event. If your repository requires
   immutable releases, stop here and implement draft promotion first; do not
   weaken repository rules to run this workflow. See GitHub's
   [immutable release procedure](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).
5. Confirm the release workflow succeeds, the four release assets exist, and
   the GHCR package can be pulled anonymously. Check its visibility in GitHub
   Packages settings and make it public if necessary. Repository visibility
   alone is not a substitute for verifying package access.

Publishing the release starts the workflow; the release page can therefore
exist temporarily without its assets. If a gate fails, nothing is published by
the publish job. Publishing to GHCR and attaching GitHub assets are separate
operations, not an atomic transaction: if upload fails after the image push,
inspect the partial state before retrying. Do not move a released tag or reuse
a version for different code. Asset uploads deliberately omit `--clobber`.
If repository rules enforce immutable releases, use a future draft-release
promotion workflow instead of bypassing those rules.

Authentication uses the workflow's `GITHUB_TOKEN`: `contents: write` to attach
release assets and `packages: write` for GHCR. The build/test job has only
`contents: read`. No Docker Hub password, model key or external graph credentials
are needed. Restrict who can create repository releases. GitHub environments
and additional approval gates can be added later if needed.

## Local Checks (No Publication)

```bash
make sync
make lint
make test
make build
make check-release RELEASE_TAG=v0.1.0
make test-distribution
```

Use a clean `dist/`: the audit rejects old or unrelated artifacts. It checks
tag/project/lock agreement, wheel metadata, package/profile inclusion and
distribution allowlists before writing `SHA256SUMS`. Source archives exclude
results, datasets, documentation builds, tests and local investigation folders.
This inventory check is not a general secret scanner; review package source
before releasing it.

`make test-distribution` uses its own disposable synthetic Neo4j. It does not
connect to Company, call an LLM or require benchmark files. See the
[distribution test coverage](library-and-server.md#reproducible-distribution-smoke).

The release job installs the source distribution in a fresh environment,
installs the wheel outside the checkout and tests the actual HTTP image.
For release builds, Docker's named context selects the already-built wheel:

```bash
docker buildx build --load --platform linux/amd64 \
  --build-context wheels=./dist --tag ana-release:test .
ANA_TEST_DIST_DIR="$PWD/dist" ANA_TEST_SERVICE_IMAGE=ana-release:test \
  make test-distribution
```

These overrides are for local/CI artifact verification. The fixture leaves an
externally supplied image in place; it still removes only the containers and
network it creates. Remove `ana-release:test` yourself when finished.
Ordinary `make docker-build` needs no `dist/`: the Dockerfile builds a wheel
internally and installs it into the runtime. Neither path runs editable source.
Service dependencies come from `uv.lock`; the runtime does not contain the
checkout, datasets, results or credentials.

The workflow saves the tested image and passes it to the separate publish job.
That job loads and pushes it without rebuilding. The same wheel bytes are
uploaded as a release asset. Dry-run workflow artifacts expire according to
GitHub retention settings (the large image artifact is retained for three days).

## Install a Published Release

These commands work **only after the corresponding release has completed**.
For the library, download the wheel and `SHA256SUMS` from the GitHub Release
(download the source archive too if checking the full checksum file):

```bash
sha256sum --check SHA256SUMS
uv venv
uv pip install ./agent_native_graph-0.1.0-py3-none-any.whl
```

On macOS use `shasum -a 256 -c SHA256SUMS`. For the HTTP extra, install
`'./agent_native_graph-0.1.0-py3-none-any.whl[service]'` instead. PyPI name-based
installation is not promised by this workflow.

To use the prebuilt container, replace the source-built image in the
[server instructions](library-and-server.md#http-server) with:

```bash
docker pull ghcr.io/paoloalbano/agent-native-graph:0.1.0
```

Keep the same authentication file mount, Neo4j environment variables and
loopback port mapping; the image bundles neither Neo4j nor graph data. For
reproducible deployments use `ghcr.io/paoloalbano/agent-native-graph@sha256:...`
from `image-digest.txt`, rather than relying on a tag alone. An existing Neo4j
instance is still required. The current one-worker/session-local limitations
remain unchanged.
